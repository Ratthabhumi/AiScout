import streamlit as st
import subprocess
import pandas as pd
import time
import os
import re
import json

try:
    import plotly.graph_objects as go
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

try:
    from google import genai
    from dotenv import load_dotenv
    load_dotenv()
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
    HAS_GEMINI = bool(GEMINI_API_KEY)
except ImportError:
    HAS_GEMINI = False
    client = None

DB_PATH = os.path.join(os.getenv("DATA_DIR", "."), "scout_brain.db")

try:
    import scout_db
    HAS_DB = os.path.exists(DB_PATH)
except ImportError:
    HAS_DB = False

HAS_GRAPH = os.path.exists("graph_engine.py")

LOG_FILE   = "ai_scout_progress.txt"
STATE_FILE = "scout_state.json"

st.set_page_config(page_title="Mew's AI Scout Dashboard", page_icon="🤖", layout="wide")
st.title("🤖 Mew's AI Scout: Progression Dashboard")
st.markdown("---")




@st.cache_data(ttl=60)
def parse_log(file_path):
    if not os.path.exists(file_path):
        return pd.DataFrame()
    data = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            ts   = re.search(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]", line)
            exp  = re.search(r"\+(\d+) EXP", line)
            gold = re.search(r"\+(\d+) Gold", line)
            if not (ts and exp):
                continue
            raw = line[ts.end():].strip()
            msg = re.split(r"\|\s*\+\d+ EXP", raw)[0].strip(" |")
            data.append({
                "Timestamp":   pd.to_datetime(ts.group(1)),
                "Message":     msg,
                "EXP_Gained":  int(exp.group(1)),
                "Gold_Gained": int(gold.group(1)) if gold else 0
            })
    return pd.DataFrame(data)


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def generate_content_with_retry(prompt, max_attempts=3):
    if not HAS_GEMINI or client is None:
        return None, "ไม่มี Gemini API"
    delay = 2
    for attempt in range(max_attempts):
        try:
            res = client.models.generate_content(model="gemini-2.5-flash-lite", contents=prompt)
            return res.text, None
        except Exception as e:
            if attempt == max_attempts - 1:
                return None, str(e)
            time.sleep(delay)
            delay *= 2
    return None, "หมดความพยายาม"


df    = parse_log(LOG_FILE)
state = load_state()

tab1, tab2, tab3 = st.tabs(["📊 Dashboard", "🧠 Brain Graph", "📡 Intel"])


with tab1:
    if not df.empty:
        if state:
            total_exp     = state["exp"]
            total_gold    = state["gold"]
            current_level = state["level"]
        else:
            total_exp     = df["EXP_Gained"].sum()
            total_gold    = df["Gold_Gained"].sum()
            current_level = (total_exp // 100) + 1

        col1, col2, col3 = st.columns(3)
        col1.metric("⭐ Current Level",    f"Lv. {current_level}")
        col2.metric("✨ Total EXP",        f"{total_exp:,} XP")
        col3.metric("💰 Total Gold Found", f"{total_gold:,} $")
    else:
        st.warning("⚠️ ยังไม่พบข้อมูล Log กรุณารอให้บอทรันสักพัก...")

    if not df.empty:
        st.subheader("📈 Progression: EXP Cumulative Growth")
        df_cumulative = (df.set_index("Timestamp")
                           .resample("1h").sum(numeric_only=True).fillna(0))
        df_cumulative["Cumulative_EXP"] = df_cumulative["EXP_Gained"].cumsum()
        st.line_chart(df_cumulative["Cumulative_EXP"])

    if state and "skill_exp" in state:
        st.subheader("🧠 Skill Tree: Neural Map")
        sk     = state["skill_exp"]
        labels = ["🛡️ Security", "☁️ Cloud/Infra", "🤖 AI/Business"]
        values = [sk.get("security", 0), sk.get("cloud", 0), sk.get("ai_biz", 0)]

        col_radar, col_bars = st.columns([1, 1])
        with col_radar:
            if HAS_PLOTLY:
                fig = go.Figure(go.Scatterpolar(
                    r=values + [values[0]], theta=labels + [labels[0]],
                    fill="toself", line_color="#6366f1",
                    fillcolor="rgba(99,102,241,0.25)",
                ))
                fig.update_layout(
                    polar=dict(
                        bgcolor="rgba(0,0,0,0)",
                        radialaxis=dict(visible=True, gridcolor="#334155"),
                        angularaxis=dict(gridcolor="#334155"),
                    ),
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    showlegend=False, margin=dict(l=40, r=40, t=40, b=40), height=320,
                )
                st.plotly_chart(fig, width='stretch')
            else:
                skill_df = pd.DataFrame({"Skill": labels, "EXP": values}).set_index("Skill")
                st.bar_chart(skill_df)

        with col_bars:
            st.markdown("**Skill EXP Breakdown**")
            total_sk = sum(values) or 1
            for label, val in zip(labels, values):
                pct = int(val / total_sk * 100)
                st.markdown(f"{label}")
                st.progress(pct / 100, text=f"{val:,} XP  ({pct}%)")

    st.subheader("📁 Harvest Mode: Latest Farmed Items (Gold)")
    if HAS_DB:
        gold_items = scout_db.get_gold_items(limit=15)
        if gold_items:
            for item in gold_items:
                ts      = item["timestamp"]
                title   = item["title"]
                source  = item["source"]
                insight = item["insight"]

                with st.expander(f"💎 {title} [{source}]"):
                    st.caption(f"📅 {ts} | 💡 {insight}")
                    c1, c2, _ = st.columns([1, 1, 2])

                    with c1:
                        if st.button("🔗 LinkedIn Post", key=f"linkedin_{ts}"):
                            with st.spinner("กำลังร่างโพสต์..."):
                                prompt = (
                                    f"คุณคือ Security Expert เขียนโพสต์ LinkedIn ภาษาไทย "
                                    f"สรุปข่าว: '{title}' ({insight}) ให้น่าสนใจ มี Hashtag และดูเป็นมืออาชีพ"
                                )
                                text, err = generate_content_with_retry(prompt)
                                if text:
                                    st.success("สร้างเสร็จแล้ว!")
                                    st.code(text, language="markdown")
                                else:
                                    st.error(f"❌ API Error: กดปุ่มใหม่อีกครั้ง ({err[:40]})")

                    with c2:
                        if st.button("🏢 Executive Brief", key=f"exec_{ts}"):
                            with st.spinner("กำลังร่าง Brief..."):
                                prompt = (
                                    f"เขียน Executive Summary ภาษาไทย 3 bullet "
                                    f"สำหรับข่าว: '{title}' "
                                    f"โฟกัสที่ความเสี่ยงและ Business Impact"
                                )
                                text, err = generate_content_with_retry(prompt)
                                if text:
                                    st.success("สร้างเสร็จแล้ว!")
                                    st.code(text, language="markdown")
                                else:
                                    st.error(f"❌ API Error: กดปุ่มใหม่อีกครั้ง ({err[:40]})")
        else:
            st.info("ℹ️ ยังไม่พบข่าวระดับ Gold")
    else:
        st.warning("⚠️ ไม่พบ Database กรุณารัน ai_scout.py ก่อน")


with tab2:
    st.subheader("🧠 Knowledge Graph — AI Brain Visualization")

    if not HAS_DB:
        st.warning("⚠️ ไม่พบ scout_brain.db")
    else:
        db_stats    = scout_db.get_stats()
        connections = scout_db.get_total_connections()

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("🔵 Nodes (Articles)", f"{db_stats['total_articles']:,}")
        c2.metric("🔗 Connections",      f"{connections:,}")
        c3.metric("💎 Gold Drops",       f"{db_stats['gold_drops']:,}")
        c4.metric("✨ Total EXP",        f"{db_stats['total_exp']:,}")

        st.markdown("---")

        GRAPH_HTML    = "brain_graph.html"
        STALE_SECONDS = 30 * 60

        def do_rebuild():
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            return subprocess.run(
                "python graph_engine.py", shell=True,
                capture_output=True, encoding="utf-8", errors="replace",
                env=env, cwd=os.path.dirname(os.path.abspath(__file__))
            )

        graph_exists = os.path.exists(GRAPH_HTML)
        is_stale     = (not graph_exists or
                        time.time() - os.path.getmtime(GRAPH_HTML) > STALE_SECONDS)

        if is_stale:
            with st.spinner("🔄 Auto-rebuilding Brain Graph..."):
                proc = do_rebuild()
            if proc.returncode != 0:
                st.error(f"❌ Build Error: {proc.stderr[-200:]}")

        col_btn, col_synapse, col_upload, col_info = st.columns([1, 1, 1, 1])
        with col_btn:
            if st.button("🔄 Force Rebuild", width="stretch"):
                with st.spinner("กำลังสร้าง Knowledge Graph..."):
                    proc = do_rebuild()
                if proc.returncode == 0:
                    st.success("✅ Brain Graph rebuilt!")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error(f"❌ Error: {proc.stderr[-300:]}")

        with col_synapse:
            if st.button("🧬 Run Synapse Merge", width="stretch"):
                with st.spinner("🧠 กำลังให้ AI เชื่อม Entity..."):
                    try:
                        import synapse_engine
                        synced = synapse_engine.run_synapse_merge(batch_size=50)
                        if synced > 0:
                            st.success(f"✅ ประมวลผล {synced} บทความ! กด Force Rebuild เพื่อดูผล")
                            st.cache_data.clear()
                        else:
                            st.info("✅ สมองเชื่อมต่อครบหมดแล้ว!")
                    except Exception as e:
                        st.error(f"❌ Error: {e}")

        with col_upload:
            uploaded = st.file_uploader("📤 Import DB", type=["db"], label_visibility="visible")
            if uploaded:
                os.makedirs(os.path.dirname(DB_PATH) if os.path.dirname(DB_PATH) else ".", exist_ok=True)
                with open(DB_PATH, "wb") as f:
                    f.write(uploaded.read())
                st.success(f"✅ Import สำเร็จ!")
                st.cache_data.clear()
                st.rerun()

        with col_info:
            if graph_exists:
                age_min = int((time.time() - os.path.getmtime(GRAPH_HTML)) / 60)
                st.caption(f"Graph อายุ {age_min} นาที | Auto-rebuild ทุก 30 นาที")

        if os.path.exists(GRAPH_HTML):
            with open(GRAPH_HTML, "r", encoding="utf-8") as f:
                html_content = f.read()
            st.iframe(html_content, height=740, scrolling=False)

            gen_time = time.strftime('%Y-%m-%d %H:%M', time.localtime(os.path.getmtime(GRAPH_HTML)))
            st.caption(f"Generated: {gen_time} | คลิก Node เพื่อดูรายละเอียด | Drag เพื่อหมุน")
        else:
            st.info("ℹ️ กด **Force Rebuild** เพื่อสร้าง Graph ครั้งแรก")

        st.markdown("""
        **Legend:**
        🔷 `Source`  ·  💎 `Gold`  ·  🥈 `Silver`  ·  🥉 `Bronze`
        🔴 `Security`  ·  🔵 `Cloud`  ·  🟢 `AI/Biz`
        """)


with tab3:
    st.subheader("📡 Source Breakdown")
    if HAS_DB:
        src_stats = scout_db.get_source_stats()
        if src_stats:
            src_df = pd.DataFrame(src_stats)
            src_df.columns = ["Source", "Articles", "EXP", "Gold"]
            st.dataframe(src_df, width="stretch", hide_index=True)
        else:
            st.info("ยังไม่มีข้อมูล")

        st.subheader("🔥 Hot Entities (Most Mentioned)")
        entities = scout_db.get_top_entities(15)
        if entities:
            ent_df = pd.DataFrame(entities)
            ent_df.columns = ["Entity", "Type", "Mentions", "Last Seen"]
            st.dataframe(ent_df, width="stretch", hide_index=True)
        else:
            st.info("Entity จะแสดงหลังบอทฟาร์มได้ Gold ครับ")
    else:
        st.warning("⚠️ ไม่พบ Database")


st.markdown("---")
col_ts, col_vault = st.columns(2)
col_ts.caption(f"Last updated: {time.strftime('%Y-%m-%d %H:%M:%S')}")
if os.path.exists("Obsidian_Knowledge"):
    n_md    = len([f for f in os.listdir("Obsidian_Knowledge") if f.endswith(".md")])
    n_daily = 0
    daily_dir = os.path.join("Obsidian_Knowledge", "daily")
    if os.path.exists(daily_dir):
        n_daily = len([f for f in os.listdir(daily_dir) if f.endswith(".md")])
    col_vault.caption(f"🧠 Obsidian: {n_md} notes | 📋 Daily digests: {n_daily}")

time.sleep(300)
st.rerun()