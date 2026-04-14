"""
scout_db.py — AI Scout Database Engine (SQLite)
"""
import sqlite3
import os
import re
from datetime import datetime

DB_FILE = "scout_brain.db"


def get_conn():
    conn = sqlite3.connect(DB_FILE, timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS articles (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp     TEXT    NOT NULL,
                title         TEXT    NOT NULL,
                source        TEXT    DEFAULT '',
                skill         TEXT    DEFAULT 'ai_biz',
                tier          TEXT    DEFAULT 'study',
                exp_gained    INTEGER DEFAULT 0,
                gold_gained   INTEGER DEFAULT 0,
                insight       TEXT    DEFAULT '',
                obsidian_path TEXT    DEFAULT '',
                is_enriched   INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS entities (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT    NOT NULL UNIQUE,
                entity_type   TEXT    DEFAULT 'topic',
                mention_count INTEGER DEFAULT 1,
                last_seen     TEXT
            );

            CREATE TABLE IF NOT EXISTS article_entities (
                article_id INTEGER REFERENCES articles(id) ON DELETE CASCADE,
                entity_id  INTEGER REFERENCES entities(id) ON DELETE CASCADE,
                PRIMARY KEY (article_id, entity_id)
            );

            CREATE INDEX IF NOT EXISTS idx_art_ts     ON articles(timestamp);
            CREATE INDEX IF NOT EXISTS idx_art_source ON articles(source);
            CREATE INDEX IF NOT EXISTS idx_art_tier   ON articles(tier);
            CREATE INDEX IF NOT EXISTS idx_art_skill  ON articles(skill);
            CREATE INDEX IF NOT EXISTS idx_ent_count  ON entities(mention_count DESC);
        """)

        # Migration: add is_enriched column if missing (backward compat)
        try:
            conn.execute("ALTER TABLE articles ADD COLUMN is_enriched INTEGER DEFAULT 0")
        except Exception:
            pass

    print("✅ scout_brain.db ready")


def insert_article(timestamp, title, source, skill, tier,
                   exp_gained, gold_gained=0, insight="", obsidian_path=""):
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO articles
               (timestamp, title, source, skill, tier, exp_gained, gold_gained, insight, obsidian_path)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (timestamp, title, source, skill, tier, exp_gained, gold_gained, insight, obsidian_path)
        )
        return cur.lastrowid


def upsert_entity(name: str, entity_type: str, timestamp: str):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO entities (name, entity_type, mention_count, last_seen)
            VALUES (?, ?, 1, ?)
            ON CONFLICT(name) DO UPDATE SET
                mention_count = mention_count + 1,
                last_seen     = excluded.last_seen
        """, (name, entity_type, timestamp))


def link_article_entity(article_id: int, entity_name: str):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM entities WHERE name = ?", (entity_name,)
        ).fetchone()
        if row:
            conn.execute(
                "INSERT OR IGNORE INTO article_entities VALUES (?,?)",
                (article_id, row["id"])
            )


def get_stats():
    with get_conn() as conn:
        r = conn.execute("""
            SELECT
                COUNT(*)                                    AS total_articles,
                COALESCE(SUM(exp_gained), 0)               AS total_exp,
                COALESCE(SUM(gold_gained), 0)              AS total_gold,
                COUNT(CASE WHEN gold_gained > 0 THEN 1 END) AS gold_drops
            FROM articles
        """).fetchone()
        return dict(r)


def get_gold_items(limit=15):
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT timestamp, title, source, skill, tier, gold_gained, insight
            FROM articles
            WHERE gold_gained > 0
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]


def get_skill_stats():
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT skill,
                   COALESCE(SUM(exp_gained),  0) AS exp,
                   COALESCE(SUM(gold_gained), 0) AS gold,
                   COUNT(*)                       AS count
            FROM articles
            GROUP BY skill
        """).fetchall()
        return {r["skill"]: dict(r) for r in rows}


def get_source_stats():
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT source,
                   COUNT(*)                       AS count,
                   COALESCE(SUM(exp_gained),  0) AS exp,
                   COALESCE(SUM(gold_gained), 0) AS gold
            FROM articles
            GROUP BY source
            ORDER BY count DESC
        """).fetchall()
        return [dict(r) for r in rows]


def get_top_entities(limit=10):
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT name, entity_type, mention_count, last_seen
            FROM entities
            ORDER BY mention_count DESC
            LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]


def get_today_stats(date_str=None):
    if not date_str:
        date_str = datetime.now().strftime('%Y-%m-%d')
    with get_conn() as conn:
        r = conn.execute("""
            SELECT
                COUNT(*)                                    AS articles,
                COALESCE(SUM(exp_gained),  0)              AS exp,
                COALESCE(SUM(gold_gained), 0)              AS gold,
                COUNT(CASE WHEN gold_gained > 0 THEN 1 END) AS gold_drops
            FROM articles
            WHERE timestamp LIKE ?
        """, (f"{date_str}%",)).fetchone()
        return dict(r)


def get_total_connections():
    with get_conn() as conn:
        r = conn.execute("SELECT COUNT(*) AS c FROM article_entities").fetchone()
        return r["c"]


def migrate_from_log(log_file="ai_scout_progress.txt"):
    if not os.path.exists(log_file):
        return 0

    with get_conn() as conn:
        count = conn.execute("SELECT COUNT(*) AS c FROM articles").fetchone()["c"]
        if count > 0:
            print(f"✅ DB มีข้อมูลอยู่แล้ว {count:,} รายการ — ข้าม migration")
            return 0

    pattern = re.compile(
        r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] "
        r"(.*?) \| \+(\d+) EXP(?:.*?\+(\d+) Gold)?"
    )

    SKILL_KEYWORDS = {
        "security": ["fortinet", "fortigate", "palo alto", "cisco", "cve", "ransomware",
                     "malware", "exploit", "firewall", "breach", "vulnerability", "patch"],
        "cloud":    ["aws", "azure", "cloud", "kubernetes", "server", "storage", "deploy",
                     "nas", "docker", "infrastructure"],
    }

    def guess_skill(title):
        tl = title.lower()
        for sk, kws in SKILL_KEYWORDS.items():
            if any(k in tl for k in kws):
                return sk
        return "ai_biz"

    migrated = 0
    with open(log_file, "r", encoding="utf-8") as f:
        for line in f:
            m = pattern.search(line)
            if not m:
                continue
            ts, msg, exp = m.group(1), m.group(2), int(m.group(3))
            gold = int(m.group(4)) if m.group(4) else 0

            title = re.sub(r"^(📖 ศึกษาข้อมูล:|💎 พบโอกาส!|💎 พบความรู้/โอกาส!|🏹.*?:)", "", msg)
            title = re.sub(r"\[.*?\]", "", title).strip(" |")
            tier  = "gold" if gold >= 15 else ("silver" if gold >= 8 else ("bronze" if gold > 0 else "study"))

            insert_article(
                timestamp=ts, title=title[:200],
                source="Blognone (migrated)",
                skill=guess_skill(title), tier=tier,
                exp_gained=exp, gold_gained=gold
            )
            migrated += 1

    print(f"📦 Migration: {migrated:,} รายการ")
    return migrated


if __name__ == "__main__":
    init_db()
