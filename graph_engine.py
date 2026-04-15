"""
graph_engine.py v2 — AI Scout Knowledge Brain (3D Force Graph)
Uses: vasturiano/3d-force-graph (Three.js + WebGL via CDN)
No pip install needed - CDN only
"""
import sqlite3
import os
import json

DB_FILE    = os.path.join(os.getenv("DATA_DIR", "."), "scout_brain.db")
OUTPUT_HTML = "brain_graph.html"


COLORS = {
    "source":          "#6366f1",
    "gold":            "#fde047",
    "silver":          "#e2e8f0",
    "bronze":          "#b45309",
    "entity_security": "#ef4444",
    "entity_cloud":    "#38bdf8",
    "entity_ai_biz":   "#4ade80",
    "entity_default":  "#64748b",
}


def _get_conn():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def build_brain_graph(max_articles=200, output_html=OUTPUT_HTML):
    if not os.path.exists(DB_FILE):
        print("[ERROR] scout_brain.db not found - run scout_db.py first")
        return False

    conn = _get_conn()
    nodes, links, node_ids = [], [], set()

    # ── 1. Source Nodes ────────────────────
    for s in conn.execute(
        "SELECT source, COUNT(*) AS n, COALESCE(SUM(gold_gained),0) AS g "
        "FROM articles GROUP BY source"
    ).fetchall():
        nid = f"src:{s['source']}"
        nodes.append({
            "id": nid, "label": s["source"], "group": "source",
            "color": COLORS["source"],
            "val": 10 + s["n"] * 0.25,
            "desc": f"Source: {s['source']}\nArticles: {s['n']} | Gold: {s['g']}"
        })
        node_ids.add(nid)

    # ── 2. Article Nodes ───────────────────
    for a in conn.execute("""
        SELECT id, title, source, skill, tier, gold_gained
        FROM articles WHERE tier IN ('gold','silver','bronze')
        ORDER BY timestamp DESC LIMIT ?
    """, (max_articles,)).fetchall():
        nid = f"art:{a['id']}"
        title_short = a["title"][:50] + ("…" if len(a["title"]) > 50 else "")
        
        # เพิ่มขนาดให้ต่างกันนิดหน่อยให้สมดุลแบบไม่พัง
        nodes.append({
            "id": nid, "label": title_short, "group": a["tier"],
            "color": COLORS.get(a["tier"], "#475569"),
            "val": 3 + (a["gold_gained"] * 0.6 if a["tier"] == "gold" else 1),
            "desc": f"[{a['tier'].upper()}] {a['title']}\nSkill: {a['skill']} | Gold+{a['gold_gained']}"
        })
        node_ids.add(nid)
        src_nid = f"src:{a['source']}"
        if src_nid in node_ids:
            links.append({"source": src_nid, "target": nid,
                          "color": "rgba(99,102,241,0.35)"})

    # ── 3. Entity Nodes ────────────────────
    for e in conn.execute("""
        SELECT name, entity_type, mention_count FROM entities
        WHERE mention_count >= 2 ORDER BY mention_count DESC LIMIT 60
    """).fetchall():
        nid = f"ent:{e['name']}"
        color = COLORS.get(f"entity_{e['entity_type']}", COLORS["entity_default"])
        nodes.append({
            "id": nid, "label": e["name"], "group": "entity",
            "color": color,
            "val": 5 + e["mention_count"] * 2.5,
            "desc": f"Entity: {e['name']}\nType: {e['entity_type']} | Mentions: {e['mention_count']}"
        })
        node_ids.add(nid)

    # ── 4. Article-Entity Links ────────────
    for lk in conn.execute("""
        SELECT ae.article_id, e.name, e.entity_type
        FROM article_entities ae
        JOIN entities e ON ae.entity_id = e.id
        JOIN articles a ON ae.article_id = a.id
        WHERE a.tier IN ('gold','silver','bronze') AND e.mention_count >= 2
    """).fetchall():
        src = f"art:{lk['article_id']}"
        tgt = f"ent:{lk['name']}"
        if src in node_ids and tgt in node_ids:
            c = COLORS.get(f"entity_{lk['entity_type']}", "rgba(239,68,68,0.4)")
            links.append({"source": src, "target": tgt, "color": c})

    conn.close()

    html = _build_html({"nodes": nodes, "links": links})
    with open(output_html, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"[OK] 3D Brain Graph -> {output_html} | Nodes: {len(nodes)} | Edges: {len(links)}")
    return len(nodes), len(links)


def _build_html(graph_data):
    data_json  = json.dumps(graph_data, ensure_ascii=False)
    n_nodes    = len(graph_data["nodes"])
    n_edges    = len(graph_data["links"])

    return f"""<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="utf-8">
<title>AI Scout — Knowledge Brain 3D</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap');
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
  background: #04080f;
  overflow: hidden;
  font-family: 'Inter', 'Segoe UI', sans-serif;
}}
#graph {{ width:100vw; height:100vh; }}

/* ── HUD top-left ── */
#hud {{
  position:fixed; top:20px; left:22px; z-index:100;
  pointer-events:none;
}}
#hud-title {{
  font-size:13px; font-weight:600;
  letter-spacing:.12em;
  color:rgba(99,102,241,.95);
  text-shadow: 0 0 18px rgba(99,102,241,1), 0 0 40px rgba(99,102,241,.5);
  margin-bottom:10px;
}}
.hud-stat {{
  font-size:11px;
  color:rgba(148,163,184,.75);
  margin:3px 0;
}}
.hud-val {{
  color:#e2e8f0; font-weight:600;
}}

/* ── Tooltip ── */
#tooltip {{
  position:fixed; display:none;
  background:rgba(8,12,28,.97);
  border:1px solid rgba(99,102,241,.55);
  border-radius:10px;
  padding:10px 14px;
  color:#e2e8f0; font-size:12px;
  max-width:300px; z-index:200;
  box-shadow: 0 0 24px rgba(99,102,241,.35);
  white-space:pre-wrap; line-height:1.6;
  pointer-events:none;
  backdrop-filter:blur(8px);
}}

/* ── Legend bottom-left ── */
#legend {{
  position:fixed; bottom:22px; left:22px; z-index:100;
  display:grid; grid-template-columns:1fr 1fr; gap:4px 18px;
  pointer-events:none;
}}
.leg-item {{
  display:flex; align-items:center; gap:6px;
  font-size:11px; color:rgba(148,163,184,.7);
}}
.leg-dot {{
  width:9px; height:9px; border-radius:50%;
  flex-shrink:0;
  box-shadow: 0 0 6px currentColor;
}}

/* ── Controls hint ── */
#controls {{
  position:fixed; bottom:22px; right:22px; z-index:100;
  font-size:10px; color:rgba(99,102,241,.45);
  text-align:right; line-height:1.8;
  pointer-events:none;
}}
</style>
</head>
<body>

<div id="hud">
  <div id="hud-title">&#x1F9E0; AI SCOUT &mdash; KNOWLEDGE BRAIN</div>
  <div class="hud-stat">Nodes &nbsp;<span class="hud-val">{n_nodes}</span></div>
  <div class="hud-stat">Connections &nbsp;<span class="hud-val">{n_edges}</span></div>
</div>

<div id="tooltip"></div>
<div id="graph"></div>

<div id="legend">
  <div class="leg-item"><span class="leg-dot" style="background:#6366f1;color:#6366f1"></span>Source</div>
  <div class="leg-item"><span class="leg-dot" style="background:#fde047;color:#fde047"></span>Gold</div>
  <div class="leg-item"><span class="leg-dot" style="background:#e2e8f0;color:#e2e8f0"></span>Silver</div>
  <div class="leg-item"><span class="leg-dot" style="background:#b45309;color:#b45309"></span>Bronze</div>
  <div class="leg-item"><span class="leg-dot" style="background:#ef4444;color:#ef4444"></span>Security</div>
  <div class="leg-item"><span class="leg-dot" style="background:#38bdf8;color:#38bdf8"></span>Cloud</div>
  <div class="leg-item"><span class="leg-dot" style="background:#4ade80;color:#4ade80"></span>AI/Biz</div>
</div>

<div id="controls">
  Drag to rotate &nbsp;|&nbsp; Scroll to zoom<br>
  Click node to focus
</div>

<script src="https://cdn.jsdelivr.net/npm/3d-force-graph@1.73.3/dist/3d-force-graph.min.js" onerror="this.onerror=null;this.src='https://unpkg.com/3d-force-graph@1.73.3/dist/3d-force-graph.min.js';"></script>
<script>
const DATA = {data_json};
const GraphDiv = document.getElementById('graph');

// ✅ WebGL Diagnostic Check
function hasWebGL() {{
    try {{
        const canvas = document.createElement('canvas');
        return !!(window.WebGLRenderingContext && (canvas.getContext('webgl') || canvas.getContext('experimental-webgl')));
    }} catch(e) {{ return false; }}
}}

if (!hasWebGL()) {{
    GraphDiv.innerHTML = '<div style="color:#ef4444; padding:100px; text-align:center; font-family:sans-serif;">' +
        '<h2>⚠️ WebGL Not Supported</h2>' +
        '<p>บราวเซอร์ของคุณบล็อกการใช้งานการ์ดจอ (Graphics Acceleration)<br>' +
        'กรุณาเปิด <b>Hardware Acceleration</b> ในช่อง Settings ของบราวเซอร์ครับ</p></div>';
}} else if (typeof ForceGraph3D === 'undefined') {{
    GraphDiv.innerHTML = '<div style="color:#ef4444; padding:100px; text-align:center; font-family:sans-serif;">' +
        '<h2>⚠️ Script Load Failed</h2>' +
        '<p>ไม่สามารถโหลดสคริปต์วาดกราฟได้ กรุณาเช็คการเชื่อมต่ออินเทอร์เน็ต<br>' +
        'หรือลองปิดโปรแกรมบล็อกโฆษณา (AdBlock) ครับ</p></div>';
}} else {{
    try {{
        const Graph = ForceGraph3D()(GraphDiv)
          .graphData(DATA)
          .backgroundColor('#04080f')


  // Nodes
  .nodeLabel(() => '')      // ใช้ tooltip เอง
  .nodeColor(n => n.color || '#6366f1')
  .nodeVal(n => n.val || 4)
  .nodeOpacity(0.95)
  .nodeResolution(20)

  // Links
  .linkColor(l => l.color || 'rgba(255,255,255,0.12)')
  .linkOpacity(0.55)
  .linkWidth(0.4)
  .linkDirectionalParticles(3)
  .linkDirectionalParticleWidth(1.8)
  .linkDirectionalParticleSpeed(d => 0.003 + Math.random() * 0.002)
  .linkDirectionalParticleColor(l => l.color || '#6366f1')

  // Hover tooltip
  .onNodeHover(node => {{
    document.body.style.cursor = node ? 'pointer' : 'default';
    if (node) {{
      tooltip.style.display = 'block';
      tooltip.textContent = node.desc || node.label;
    }} else {{
      tooltip.style.display = 'none';
    }}
  }})

  // Click → zoom to node
  .onNodeClick(node => {{
    const dist = 120;
    const distRatio = 1 + dist / Math.hypot(node.x, node.y, node.z);
    Graph.cameraPosition(
      {{ x: node.x * distRatio, y: node.y * distRatio, z: node.z * distRatio }},
      node,
      1200
    );
  }});

// Track mouse for tooltip position
document.addEventListener('mousemove', e => {{
  tooltip.style.left = (e.clientX + 14) + 'px';
  tooltip.style.top  = (e.clientY + 14) + 'px';
}});

// Slow auto-rotation (stop when user interacts)
let rotating = true;
let angle = 0;
const rotTimer = setInterval(() => {{
  if (!rotating) return;
  Graph.cameraPosition({{
    x: 600 * Math.sin(angle),
    z: 600 * Math.cos(angle)
  }});
  angle += Math.PI / 2400;
}}, 30);

// Stop rotation on user drag
document.getElementById('graph').addEventListener('mousedown', () => {{ rotating = false; }});
document.getElementById('graph').addEventListener('wheel',     () => {{ rotating = false; }});

// Handle Dynamic Resizing for Streamlit Tabs
const resizeObserver = new ResizeObserver(entries => {{
  for (let entry of entries) {{
    if (entry.contentRect.width > 0 && entry.contentRect.height > 0) {{
      Graph.width(entry.contentRect.width).height(entry.contentRect.height);
    }}
  }}
}});
resizeObserver.observe(document.body);
    }} catch (err) {{
        console.error(err);
        GraphDiv.innerHTML = '<div style="color:#ef4444; padding:100px; text-align:center; font-family:sans-serif;">' +
            '<h2>⚠️ Graph Rendering Error</h2>' +
            '<p>เกิดข้อผิดพลาดในการวาดกราฟ: ' + err.message + '</p></div>';
    }}
}}
</script>
</body>
</html>"""


if __name__ == "__main__":
    result = build_brain_graph()
    if result:
        print("[OK] Open brain_graph.html in your browser!")
