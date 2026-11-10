"""RQ1 plots (plotly) from results.csv -> results/rq1_plots.html. Usage: python rq1_plotly.py [results.csv]"""
import csv, math, sys
from collections import defaultdict
import plotly.graph_objects as go
from plotly.subplots import make_subplots

SRC = sys.argv[1] if len(sys.argv) > 1 else "results.csv"
MODELS = [("gemini", "Gemini 3.8 Flash", "#2a78d6"), ("sonnet", "Claude Sonnet 5.5", "#eb6834"),
          ("gpt6", "GPT-6 Sol", "#1baf7a")]
DEFENSES = [("none", "No defense"), ("spotlighting_with_delimiting", "Spotlighting"),
            ("repeat_user_prompt", "Repeat user prompt")]

def wilson(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0
    p = k / n; d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0, c - h), min(1, c + h)

rows = list(csv.DictReader(open(SRC)))
benign, attacked, asr = defaultdict(list), defaultdict(list), defaultdict(list)
for r in rows:
    key = (r["model"], r["defense"])
    if r["injection_task"] == "none":
        benign[key].append(int(r["utility"]))
    else:
        attacked[key].append(int(r["utility"]))
        asr[key].append(int(r["attack_success"] or 0))

def panel(fig, col, data, title):
    for m, label, color in MODELS:
        ys, lo, hi, txt = [], [], [], []
        for d, _ in DEFENSES:
            v = data.get((m, d), [])
            k, n = sum(v), len(v)
            p = k / n if n else 0
            l, h = wilson(k, n)
            ys.append(p * 100); lo.append((p - l) * 100); hi.append((h - p) * 100)
            txt.append(f"{label}<br>{d}<br>{k}/{n} = {p:.0%}<br>95% CI {l:.0%}-{h:.0%}")
        fig.add_trace(go.Bar(name=label, x=[n for _, n in DEFENSES], y=ys, marker_color=color,
                             legendgroup=m, showlegend=(col == 1), hovertext=txt, hoverinfo="text",
                             error_y=dict(type="data", symmetric=False, array=hi, arrayminus=lo,
                                          color="#52514e", thickness=1.5, width=4)), row=1, col=col)
    fig.update_yaxes(range=[0, 105], title_text="%", row=1, col=col)

fig = make_subplots(rows=1, cols=3, shared_yaxes=False, horizontal_spacing=0.07,
                    subplot_titles=("Utility, no attack", "Utility under attack", "Attack success rate (ASR)"))
panel(fig, 1, benign, ""); panel(fig, 2, attacked, ""); panel(fig, 3, asr, "")
fig.update_yaxes(range=[0, 40], row=1, col=3)  # ASR is 0 everywhere; show CI headroom
fig.update_layout(barmode="group", bargap=0.25, template="plotly_white", height=480, width=1300,
                  title="RQ1: AgentDojo workspace, 3 models x 3 defenses (bars = rate, whiskers = Wilson 95% CI)",
                  legend=dict(orientation="h", y=-0.15), font=dict(color="#0b0b0b"),
                  margin=dict(t=90, b=90))
out = "results/rq1_plots.html"
fig.write_html(out, include_plotlyjs="cdn")
print("wrote", out)
for m, label, _ in MODELS:
    for d, dn in DEFENSES:
        k = asr.get((m, d), []); print(f"{label:18} {dn:20} benign n={len(benign.get((m,d),[]))} attacked n={len(k)} ASR={sum(k)}")
