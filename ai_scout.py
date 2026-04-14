import feedparser
import time
import random
import os
import re
import json
import requests
from google import genai
import scout_db
import synapse_engine

GEMINI_API_KEY = "AIzaSyCufQkV9Zn-GGCt5UO56Lae7Qtepm7En-I"
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1493675753454178405/S72smIixkuqs0YrbIu8Cn6di1CRVQ2SN4fvXmxi5AupmAdKdEQVrNeDQ-691NH4mz0Qr" 

RSS_FEEDS = [
    ("Blognone",         "https://www.blognone.com/node/feed"),
    ("Fortinet",         "https://www.fortinet.com/blog/feed"),
    ("Unit42",           "https://unit42.paloaltonetworks.com/feed/"),
    ("Dark Reading",     "https://www.darkreading.com/rss.xml"),
    ("Hacker News",      "https://news.ycombinator.com/rss"),
    ("Cisco Talos",      "https://blog.talosintelligence.com/rss/"),
    ("BleepingComputer", "https://www.bleepingcomputer.com/feed/"),
    ("The Hacker News",  "https://feeds.feedburner.com/TheHackersNews"),
    ("TechCrunch",       "https://techcrunch.com/feed/"),
]

SAVE_FILE      = "ai_scout_progress.txt"
SEEN_FILE      = "seen_titles.txt"
STATE_FILE     = "scout_state.json"
OBSIDIAN_VAULT = "Obsidian_Knowledge"
DAILY_DIR      = os.path.join(OBSIDIAN_VAULT, "daily")

client = genai.Client(api_key=GEMINI_API_KEY)

SKILL_TREE = {
    "security": {
        "icon": "🛡️", "name": "Security",
        "keywords": [
            "fortinet", "fortigate", "fortios", "palo alto", "cisco", "firewall",
            "ngfw", "ips", "ids", "waf", "soc", "siem", "cve", "vulnerability",
            "exploit", "ransomware", "malware", "phishing", "zero-day", "zero day",
            "breach", "patch", "threat", "vpn", "attack", "intrusion", "backdoor",
            "botnet", "ddos", "pentest", "red team", "blue team", "security"
        ]
    },
    "cloud": {
        "icon": "☁️", "name": "Cloud/Infra",
        "keywords": [
            "aws", "azure", "cloud", "kubernetes", "docker", "container",
            "deploy", "server", "infrastructure", "nas", "storage", "devops",
            "terraform", "datacenter", "backup", "network", "switch", "router",
            "linux", "windows server", "vmware", "hypervisor", "san", "vlan"
        ]
    },
    "ai_biz": {
        "icon": "🤖", "name": "AI/Business",
        "keywords": [
            "ai", "llm", "machine learning", "automation", "robot", "genai",
            "gpt", "gemini", "claude", "chatbot", "revenue", "startup",
            "investment", "billion", "million", "market", "profit", "acquisition",
            "ipo", "funding", "saas", "model", "neural", "inference"
        ]
    }
}

TIER_CONFIG = {
    "gold":   {"icon": "💎", "min_score": 4, "chance": 1.00, "gold_range": (15, 25)},
    "silver": {"icon": "🥈", "min_score": 2, "chance": 0.85, "gold_range": (8, 14)},
    "bronze": {"icon": "🥉", "min_score": 1, "chance": 0.60, "gold_range": (2,  7)},
}


class AIScout:
    def __init__(self):
        self.state = self._load_state()
        self.seen_titles = self._load_seen()

        os.makedirs(OBSIDIAN_VAULT, exist_ok=True)
        os.makedirs(DAILY_DIR, exist_ok=True)

        scout_db.init_db()
        scout_db.migrate_from_log(SAVE_FILE)

        lv   = self.state["level"]
        exp  = self.state["exp"]
        gold = self.state["gold"]
        sk   = self.state["skill_exp"]
        print(f"📥 State: Lv.{lv} | EXP:{exp:,} | Gold:{gold:,}")
        print(f"   🛡️ Security:{sk['security']:,}  ☁️ Cloud:{sk['cloud']:,}  🤖 AI/Biz:{sk['ai_biz']:,}")
        print(f"📋 จำข่าวเก่า {len(self.seen_titles):,} รายการ")

    def _load_state(self):
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
            state.setdefault("skill_exp", {"security": 0, "cloud": 0, "ai_biz": 0})
            state.setdefault("last_digest_date", "")
            return state
        return self._migrate_from_log()

    def _migrate_from_log(self):
        state = {
            "level": 1, "exp": 0, "gold": 0, "farm_count": 0,
            "skill_exp": {"security": 0, "cloud": 0, "ai_biz": 0},
            "last_digest_date": ""
        }
        if not os.path.exists(SAVE_FILE):
            return state
        pat = r"\[(.*?)\] .*? \| \+(\d+) EXP(?: \| \+(\d+) Gold)?"
        with open(SAVE_FILE, "r", encoding="utf-8") as f:
            for line in f:
                m = re.search(pat, line)
                if m:
                    state["exp"] += int(m.group(2))
                    if m.group(3):
                        state["gold"] += int(m.group(3))
        state["level"] = (state["exp"] // 100) + 1
        return state

    def _save_state(self):
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(self.state, f, ensure_ascii=False, indent=2)

    def _load_seen(self):
        if not os.path.exists(SEEN_FILE):
            return set()
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return {line.strip() for line in f if line.strip()}

    def _save_seen(self):
        with open(SEEN_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(self.seen_titles))

    def generate_daily_digest(self, target_date: str):
        if not os.path.exists(SAVE_FILE):
            return

        pat = re.compile(
            r"\[(" + target_date + r" \d{2}:\d{2}:\d{2})\] "
            r"(.*?) \| \+(\d+) EXP(?:.*?\+(\d+) Gold)?"
        )
        entries = []
        with open(SAVE_FILE, "r", encoding="utf-8") as f:
            for line in f:
                m = pat.search(line)
                if m:
                    entries.append({
                        "ts":   m.group(1),
                        "msg":  m.group(2).strip(),
                        "exp":  int(m.group(3)),
                        "gold": int(m.group(4)) if m.group(4) else 0,
                    })

        if not entries:
            return

        total_exp  = sum(e["exp"]  for e in entries)
        total_gold = sum(e["gold"] for e in entries)
        gold_items = [e for e in entries if e["gold"] > 0]

        tiers = {"gold": [], "silver": [], "bronze": []}
        for e in gold_items:
            if "[GOLD]" in e["msg"] or "💎" in e["msg"]:
                tiers["gold"].append(e)
            elif "[SILVER]" in e["msg"] or "🥈" in e["msg"]:
                tiers["silver"].append(e)
            else:
                tiers["bronze"].append(e)

        def tier_section(tier_name, icon, items):
            if not items:
                return ""
            lines = [f"## {icon} {tier_name.capitalize()} Tier\n"]
            for e in items:
                clean = re.sub(r"💎|🥈|🥉|\[GOLD\]|\[SILVER\]|\[BRONZE\]", "", e["msg"]).strip()
                lines.append(f"- {clean} | +{e['gold']} 💰")
            return "\n".join(lines) + "\n"

        content = f"""---
tags: [daily-report, scout, digest]
date: {target_date}
---
# 📊 Daily Intel Report — {target_date}

**Generated:** {time.strftime('%Y-%m-%d %H:%M:%S')}
**Articles Processed:** {len(entries)}

---

## 📈 Today's Stats

| Metric | Value |
|---|---|
| ✨ EXP Earned | +{total_exp:,} XP |
| 💰 Gold Found | +{total_gold:,} G |
| 📖 Articles | {len(entries)} |
| 💎 Gold Drops | {len(gold_items)} items |

---

{tier_section('gold',   '💎', tiers['gold'])}
{tier_section('silver', '🥈', tiers['silver'])}
{tier_section('bronze', '🥉', tiers['bronze'])}

---
*AI Scout v3.0 — Daily Digest*
"""
        out_path = os.path.join(DAILY_DIR, f"{target_date}.md")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"📝 Daily Digest → {out_path}")

    def score_article(self, title):
        tl = title.lower()
        scores = {k: sum(1 for kw in v["keywords"] if kw in tl)
                  for k, v in SKILL_TREE.items()}
        total = sum(scores.values())
        dominant = max(scores, key=scores.get) if total > 0 else "ai_biz"
        return dominant, total, scores

    def get_tier(self, score):
        for tier_name, cfg in TIER_CONFIG.items():
            if score >= cfg["min_score"]:
                return tier_name, cfg
        return None, None

    def send_discord_webhook(self, message):
        if not DISCORD_WEBHOOK_URL:
            return
        try:
            requests.post(DISCORD_WEBHOOK_URL, json={"content": message}, timeout=5)
        except Exception as e:
            print(f"⚠️ Discord Error: {e}")

    def analyze_opportunity(self, title):
        prompt = (
            f"วิเคราะห์ข่าว IT: '{title}'\n"
            f"อธิบายความสำคัญด้าน Network/Security/Cloud สั้นๆ ไม่เกิน 15 คำ"
        )
        retry_delay = 2
        for attempt in range(3):
            try:
                r = client.models.generate_content(model="gemini-2.5-flash-lite", contents=prompt)
                return r.text.strip()
            except Exception as e:
                err = str(e)
                if attempt < 2 and ("503" in err or "429" in err or "UNAVAILABLE" in err):
                    print(f"   [RETRY] Gemini Busy ({attempt+1}/3). Wait {retry_delay}s...")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    return "บทความ IT สำคัญ — ควรติดตามและศึกษาเพิ่มเติม"
        return "บทความ IT สำคัญ — ควรติดตามและศึกษาเพิ่มเติม"

    def save_to_obsidian(self, title, insight, skill, tier):
        safe = re.sub(r'[^a-zA-Z0-9ก-๙ ]', '', title).strip()[:50]
        tier_icon = TIER_CONFIG[tier]["icon"] if tier in TIER_CONFIG else "📖"
        fname = f"{tier_icon} {safe}.md"
        fpath = os.path.join(OBSIDIAN_VAULT, fname)
        sk = SKILL_TREE[skill]
        content = f"""---
tags: [scout, {tier}, {skill}]
date: {time.strftime('%Y-%m-%d')}
skill: {sk['name']}
tier: {tier}
---
# {title}

**Tier:** {tier_icon} {tier.upper()}
**Skill:** {sk['icon']} {sk['name']}
**Found:** {time.strftime('%Y-%m-%d %H:%M')}

## Analysis
{insight}

## Action Items
- [ ] ค้นข้อมูลเพิ่มเติม
- [ ] เชื่อมโยงกับ Fortigate / Palo Alto ที่รู้จัก
- [ ] หยิบไปคุยกับพี่ที่บริษัท

---
*AI Scout v3.0*
"""
        try:
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(content)
            return fpath  # BUG FIX: ต้อง return ค่า path ออกมาด้วย
        except Exception:
            return ""

    def log_event(self, message):
        ts = time.strftime('%Y-%m-%d %H:%M:%S')
        with open(SAVE_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {message}\n")
        print(f"[{ts}] {message}")

    def farm(self):
        today = time.strftime('%Y-%m-%d')
        last  = self.state.get("last_digest_date", "")
        if last and last != today:
            self.generate_daily_digest(last)
        self.state["last_digest_date"] = today

        self.state["farm_count"] += 1
        fc = self.state["farm_count"]
        source_name, rss_url = random.choice(RSS_FEEDS)

        self.log_event(f"🏹 รอบที่ {fc} (Lv.{self.state['level']}): สแกน [{source_name}]...")

        feed = feedparser.parse(rss_url)
        new_entries = [e for e in feed.entries if e.title not in self.seen_titles]

        if not new_entries:
            self.log_event(f"📭 [{source_name}] ไม่มีข้อมูลใหม่")
            self._save_state()
            return

        entries = random.sample(new_entries, min(len(new_entries), 3))

        for entry in entries:
            self.seen_titles.add(entry.title)
            self._save_seen()

            dominant_skill, total_score, _ = self.score_article(entry.title)
            sk = SKILL_TREE[dominant_skill]

            gained_exp = random.randint(20, 35)
            self.state["exp"] += gained_exp
            self.state["skill_exp"][dominant_skill] += gained_exp

            tier_name, tier_cfg = self.get_tier(total_score)

            if tier_name and random.random() < tier_cfg["chance"]:
                insight    = self.analyze_opportunity(entry.title)
                gained_gold = random.randint(*tier_cfg["gold_range"])
                self.state["gold"] += gained_gold

                msg = (
                    f"{tier_cfg['icon']} [{tier_name.upper()}][{sk['icon']}{sk['name']}] "
                    f"[{source_name}] {entry.title} | {insight} "
                    f"| +{gained_exp} EXP | +{gained_gold} Gold"
                )
                obs_path = self.save_to_obsidian(entry.title, insight, dominant_skill, tier_name)

                art_id = scout_db.insert_article(
                    timestamp=time.strftime('%Y-%m-%d %H:%M:%S'),
                    title=entry.title, source=source_name,
                    skill=dominant_skill, tier=tier_name,
                    exp_gained=gained_exp, gold_gained=gained_gold,
                    insight=insight, obsidian_path=obs_path
                )

                for kw in SKILL_TREE[dominant_skill]["keywords"]:
                    if kw in entry.title.lower():
                        scout_db.upsert_entity(kw, dominant_skill, time.strftime('%Y-%m-%d %H:%M:%S'))
                        scout_db.link_article_entity(art_id, kw)

                if tier_name == "gold":
                    self.send_discord_webhook(
                        f"\n🚨 **[GOLD DROP]** มีโอกาสน่าสนใจ!\n**หัวข้อ:** {entry.title}\n{insight}"
                    )
            else:
                msg = f"📖 [{sk['icon']}{source_name}] {entry.title} | +{gained_exp} EXP"
                scout_db.insert_article(
                    timestamp=time.strftime('%Y-%m-%d %H:%M:%S'),
                    title=entry.title, source=source_name,
                    skill=dominant_skill, tier="study",
                    exp_gained=gained_exp, gold_gained=0
                )

            self.log_event(msg)

            new_lv = (self.state["exp"] // 100) + 1
            if new_lv > self.state["level"]:
                self.state["level"] = new_lv
                sk_str = " | ".join(
                    f"{SKILL_TREE[k]['icon']}{v:,}" for k, v in self.state["skill_exp"].items()
                )
                self.log_event(f"⚡ LEVEL UP! → Lv.{new_lv} | Skills: {sk_str}")

            time.sleep(5)

        self._save_state()

        sk_str = " | ".join(
            f"{SKILL_TREE[k]['icon']}{v:,}" for k, v in self.state["skill_exp"].items()
        )
        self.log_event(f"✅ รอบ {fc} เสร็จ — EXP:{self.state['exp']:,} | Gold:{self.state['gold']:,} | {sk_str}")


if __name__ == "__main__":
    scout = AIScout()
    print("\n🚀 AI Scout v3.0 — Skill Tree Edition! (Ctrl+C เพื่อหยุด)\n")
    try:
        while True:
            scout.farm()
            try:
                print("\n🧠 Auto-Synapse Merging...")
                synapse_engine.run_synapse_merge(batch_size=10)
            except Exception as e:
                print(f"⚠️ Auto-Synapse Error: {e}")
            wait_min = random.randint(10, 20)
            print(f"\n💤 คูลดาวน์ {wait_min} นาที...\n")
            time.sleep(wait_min * 60)
    except KeyboardInterrupt:
        print("\n🛑 หยุดการทำงาน")
        scout._save_state()