"""Interactive life-graph viewer: ~/.stiti/graph.html (vis-network, opens in the browser).

Nodes = entities (sized by degree), solid edges = facts true now, dashed grey = facts that ended
(kept, never deleted). Hover an edge to see the fact, since-date and evidence episode ids.
"""
from __future__ import annotations

import html
import json
import subprocess

from ..config import CFG
from ..db import q

COLORS = {"self": "#ff9933", "person": "#e4572e", "project": "#4c8bf5", "place": "#2ea44f", "org": "#8250df",
          "event": "#d4a72c", "feeling": "#db61a2", "topic": "#57606a", "thing": "#6e7781"}


def render(open_browser: bool = True) -> str:
    ents = q("""SELECT e.id, e.name, e.kind, count(f.id) deg FROM entities e
                LEFT JOIN facts f ON (f.subj_id=e.id OR f.obj_id=e.id) AND upper_inf(f.recorded)
                WHERE e.merged_into IS NULL AND e.privacy <= 1 GROUP BY e.id""")
    facts = q("""SELECT id, subj_id, obj_id, obj_literal, predicate, fact_text, lower(valid) since, upper(valid) until,
                        source_episode_ids FROM facts WHERE upper_inf(recorded) AND privacy <= 1""")
    nodes = [{"id": e["id"], "label": e["name"], "group": e["kind"], "value": 1 + e["deg"],
              "color": COLORS.get(e["kind"], "#6e7781"), "title": f"{e['kind']} · {e['deg']} facts"} for e in ents]
    edges, lit_id = [], -1
    for f in facts:
        to = f["obj_id"]
        if to is None:  # literal object -> small leaf node
            nodes.append({"id": lit_id, "label": f["obj_literal"][:30], "shape": "box", "color": "#eaeef2",
                          "font": {"size": 10}})
            to, lit_id = lit_id, lit_id - 1
        ended = f["until"] is not None
        edges.append({"from": f["subj_id"], "to": to, "label": f["predicate"].replace("_", " "), "arrows": "to",
                      "dashes": ended, "color": {"color": "#afb8c1" if ended else "#57606a"},
                      "title": f"{f['fact_text']}\nsince {f['since']:%Y-%m-%d}"
                               + (f"\nended {f['until']:%Y-%m-%d}" if ended else "")
                               + f"\nevidence: {f['source_episode_ids']}"})
    page = f"""<!doctype html><html><head><meta charset="utf-8"><title>Stiti life graph</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<script src="https://unpkg.com/vis-network@9.1.9/standalone/umd/vis-network.min.js"></script>
<style>:root{{--bg:#fff;--fg:#1f2328}}@media (prefers-color-scheme:dark){{:root{{--bg:#0d1117;--fg:#e6edf3}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font-family:system-ui}}#g{{height:100vh}}
header{{position:fixed;top:12px;left:16px;z-index:2;font-size:14px;opacity:.85}}</style></head><body>
<header><b>Stiti · {html.escape(__import__('stiti.profile', fromlist=['name']).name())}'s life graph</b> — {len(ents)} entities · {len(facts)} facts (dashed = ended, kept forever)</header>
<div id="g"></div><script>
const nodes=new vis.DataSet({json.dumps(nodes, default=str)});
const edges=new vis.DataSet({json.dumps(edges, default=str)});
new vis.Network(document.getElementById('g'),{{nodes,edges}},{{
  nodes:{{shape:'dot',scaling:{{min:8,max:40}},font:{{color:getComputedStyle(document.body).color}}}},
  edges:{{font:{{size:10,align:'middle',color:'#8c959f',strokeWidth:0}},smooth:{{type:'dynamic'}}}},
  physics:{{stabilization:true,barnesHut:{{springLength:140}}}},interaction:{{hover:true}}}});
</script></body></html>"""
    out = CFG.home / "graph.html"
    out.write_text(page)
    if open_browser:
        subprocess.Popen(["open", str(out)])
    return html.escape(str(out))
