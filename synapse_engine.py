"""
synapse_engine.py — AI Scout Entity Extractor
Batch-processes articles to extract and merge entities into the knowledge graph.
"""
import json
import time
import sys
from google import genai
import scout_db

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

GEMINI_API_KEY = "AIzaSyCufQkV9Zn-GGCt5UO56Lae7Qtepm7En-I"
client = genai.Client(api_key=GEMINI_API_KEY)


def run_synapse_merge(batch_size=50):
    print(f"[SYNAPSE ENGINE] Starting Synapse Merge (Batch: {batch_size})...")

    conn = scout_db.get_conn()
    rows = conn.execute("""
        SELECT id, title, skill
        FROM articles
        WHERE is_enriched = 0 AND tier IN ('gold', 'silver', 'bronze')
        ORDER BY timestamp DESC
        LIMIT ?
    """, (batch_size,)).fetchall()

    if not rows:
        print("[OK] [SYNAPSE ENGINE] ไม่มีบทความใหม่ที่ต้องประมวลผล")
        conn.close()
        return 0

    articles_data = [{"id": r["id"], "title": r["title"], "skill": r["skill"]} for r in rows]
    conn.close()

    prompt = f"""คุณคือนักวิเคราะห์ Cyber Threat Intelligence
อ่าน Title ของข่าว IT จำนวน {len(articles_data)} รายการ แล้วสกัด Entity ที่สำคัญออกมา

กฎการสกัด:
1. สกัดเฉพาะชื่อเฉพาะ เช่น ชื่อบริษัท, เทคโนโลยี, กลุ่มแฮกเกอร์, มัลแวร์, CVE
2. Normalization: "GenAI"/"Generative AI"/"LLM" ให้รวมเป็น "GenAI", "MSFT" → "Microsoft"
3. type ให้ระบุว่า "security", "cloud", หรือ "ai_biz"

ส่งคืนเป็น JSON Array เท่านั้น ห้ามมี Markdown หรือข้อความอื่น:
[
  {{
    "article_id": 123,
    "entities": [
      {{"name": "Microsoft", "type": "cloud"}},
      {{"name": "CVE-2024-38063", "type": "security"}}
    ]
  }}
]

บทความ:
{json.dumps(articles_data, ensure_ascii=False, indent=2)}
"""

    print(f"[WAIT] ส่งข้อมูล {len(articles_data)} ข่าว ให้ Gemini วิเคราะห์...")

    retry_delay = 2
    response    = None

    for attempt in range(5):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash-lite",
                contents=prompt
            )
            break
        except Exception as e:
            err = str(e)
            if attempt < 4 and ("503" in err or "429" in err or "UNAVAILABLE" in err):
                print(f"[RETRY] Gemini Busy. Retry in {retry_delay}s... ({attempt+1}/5)")
                time.sleep(retry_delay)
                retry_delay *= 2
            else:
                print(f"[ERROR] {e}")
                raise e

    if not response:
        return 0

    try:
        result_text = response.text.replace("```json", "").replace("```", "").strip()
        parsed_data = json.loads(result_text)

        success_count  = 0
        added_entities = 0

        for item in parsed_data:
            a_id = item.get("article_id")
            ents = item.get("entities", [])

            for e in ents:
                e_name = e.get("name", "").strip().title()
                e_type = e.get("type", "ai_biz").lower()
                if len(e_name) > 1:
                    scout_db.upsert_entity(e_name, e_type, time.strftime('%Y-%m-%d %H:%M:%S'))
                    scout_db.link_article_entity(a_id, e_name)
                    added_entities += 1

            with scout_db.get_conn() as local_conn:
                local_conn.execute("UPDATE articles SET is_enriched = 1 WHERE id = ?", (a_id,))
            success_count += 1

        print(f"[OK] ประมวลผล {success_count} ข่าว | เชื่อม {added_entities} จุด")

    except Exception as e:
        print(f"[ERROR] Parse failed: {e}")
        raise e

    return success_count


if __name__ == "__main__":
    run_synapse_merge(50)
