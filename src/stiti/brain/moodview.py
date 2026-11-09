"""Mood timeline: ~/.stiti/mood.html — how his mood and energy moved over the last 14 days.

Built from the fused emotion stored on every one of his utterances (text + voice + baseline).
A mirror, not a diagnosis: Stiti's mood reads are hints (~41–80% accurate), shown as trends.
"""
from __future__ import annotations

import json
import subprocess

from ..config import CFG
from ..db import q

MOODS = ["happy", "calm", "tired", "stressed", "sad", "angry"]
COLORS = {"happy": "#2ea44f", "calm": "#57a6ff", "tired": "#a371f7", "stressed": "#d4a72c", "sad": "#6e7781",
          "angry": "#e4572e"}


def render(days: int = 14, open_browser: bool = True) -> str:
    rows = q("""SELECT (occurred_at AT TIME ZONE %s)::date AS d, coalesce(emotion->>'label','calm') AS m,
                       avg(coalesce((emotion->>'arousal')::real, 0.3)) AS ar, count(*) AS n
                FROM episodes WHERE speaker='user' AND emotion IS NOT NULL
                  AND occurred_at > now() - make_interval(days => %s)
                GROUP BY 1, 2 ORDER BY 1""", (CFG.tz.key, days))
    dates = sorted({str(r["d"]) for r in rows})
    series = {m: [0] * len(dates) for m in MOODS}
    energy = [0.0] * len(dates)
    counts = [0] * len(dates)
    for r in rows:
        i = dates.index(str(r["d"]))
        if r["m"] in series:
            series[r["m"]][i] += r["n"]
        energy[i] += float(r["ar"]) * r["n"]
        counts[i] += r["n"]
    energy = [round(e / c, 2) if c else None for e, c in zip(energy, counts)]
    datasets = [{"label": m, "data": series[m], "backgroundColor": COLORS[m], "stack": "mood"} for m in MOODS]
    page = f"""<!doctype html><html><head><meta charset="utf-8"><title>Stiti mood timeline</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>:root{{--bg:#fff;--fg:#1f2328;--muted:#656d76}}
@media (prefers-color-scheme:dark){{:root{{--bg:#0d1117;--fg:#e6edf3;--muted:#8d96a0}}}}
body{{margin:0;padding:24px 16px;background:var(--bg);color:var(--fg);font-family:system-ui;max-width:960px;margin:auto}}
h1{{font-size:20px;margin:0 0 4px}}p{{color:var(--muted);margin:0 0 20px;font-size:14px}}canvas{{margin-bottom:28px}}</style>
</head><body><h1>Your last {days} days</h1>
<p>Mood of what you said each day (bars) and your energy level (line). Stiti's reads are hints — trends matter, single days don't.</p>
<canvas id="m" height="140"></canvas><canvas id="e" height="80"></canvas>
<script>
const labels={json.dumps(dates)};
new Chart(document.getElementById('m'),{{type:'bar',data:{{labels,datasets:{json.dumps(datasets)}}},
  options:{{plugins:{{legend:{{position:'bottom'}}}},scales:{{x:{{stacked:true}},y:{{stacked:true,title:{{display:true,text:'messages'}}}}}}}}}});
new Chart(document.getElementById('e'),{{type:'line',data:{{labels,datasets:[{{label:'energy (arousal)',data:{json.dumps(energy)},
  borderColor:'#57a6ff',tension:.3,spanGaps:true}}]}},options:{{plugins:{{legend:{{display:false}}}},scales:{{y:{{min:0,max:1}}}}}}}});
</script></body></html>"""
    out = CFG.home / "mood.html"
    out.write_text(page)
    if open_browser:
        subprocess.Popen(["open", str(out)])
    return str(out)
