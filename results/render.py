"""Render results/v3_attempts.json into results/leaderboard.html.

    python3 results/render.py

Score = share of attempts that pass every check. Interval = 95% Wilson score
interval on that share (right for small n of pass/fail attempts).
"""

import json
import math
from html import escape
from pathlib import Path

HERE = Path(__file__).parent
NAMES = {
    "claude-opus-5-5": ("Claude Opus 5.5", "Anthropic"),
    "claude-fable-5-2": ("Claude Fable 5.2", "Anthropic"),
    "claude-sonnet-5-5": ("Claude Sonnet 5.5", "Anthropic"),
    "claude-haiku-5-5": ("Claude Haiku 5.5", "Anthropic"),
    "gpt-6-astra": ("GPT-6 Astra", "OpenAI"),
    "gpt-6.1-sol": ("GPT-6.1 Sol", "OpenAI"),
}


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = k / n
    den = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, mid - half), min(1.0, mid + half)


def failure_kind(a: dict) -> str:
    """How a failed attempt went wrong, read from the grader's check lines."""
    fails = [c for c in a["checks"] if c.startswith("FAIL")]
    if any("NOT sent to director" in c for c in fails):
        return "overasked"     # sent approval requests the team wouldn't have
    if any("sent to director for approval" in c for c in fails):
        return "never_asked"   # logged everything, asked nobody
    return "other"


KIND_TEXT = {"never_asked": "never asked anyone", "overasked": "followed the old $5k rule",
             "other": "other mistakes"}


def summarize(attempts: list[dict]) -> list[dict]:
    rows = []
    for model in sorted({a["model"] for a in attempts}):
        r = {"model": model, "name": NAMES.get(model, (model, ""))[0],
             "lab": NAMES.get(model, ("", ""))[1]}
        for v in ("hidden", "written"):
            scored = [a for a in attempts if a["model"] == model and a["version"] == v
                      and a["status"] == "FINISHED" and a["reward"] is not None]
            k, n = sum(int(a["reward"]) for a in scored), len(scored)
            lo, hi = wilson(k, n)
            r[v] = {"k": k, "n": n, "p": k / n if n else 0.0, "lo": lo, "hi": hi}
            kinds = [failure_kind(a) for a in scored if a["reward"] != 1]
            r[v]["fails"] = {kd: kinds.count(kd) for kd in KIND_TEXT if kinds.count(kd)}
        rows.append(r)
    rows = [r for r in rows if r["hidden"]["n"]]
    rows.sort(key=lambda r: (-r["hidden"]["p"], -r["written"]["p"], r["name"]))
    return rows


def pct(x: float) -> str:
    return f"{round(x * 100)}%"


def render(rows: list[dict]) -> str:
    n_per = sorted({r["hidden"]["n"] for r in rows})
    n_txt = f"{n_per[0]}" if len(n_per) == 1 else f"{n_per[0]} to {n_per[-1]}"
    grid = "".join(f'<i style="left:{t}%"></i>' for t in range(20, 101, 20))
    row_html = []
    for i, r in enumerate(rows, 1):
        h, w = r["hidden"], r["written"]
        why = ", ".join(f"{KIND_TEXT[k]} ({c})" for k, c in h["fails"].items())
        why_html = f'<span class="why">Misses: {why}</span>' if why else ""
        tip = (f"{escape(r['name'])}|Rule only in past work: {h['k']}/{h['n']} passed "
               f"({pct(h['p'])}, 95% range {pct(h['lo'])} to {pct(h['hi'])})|"
               f"Rule written in an email: {w['k']}/{w['n']} passed ({pct(w['p'])})"
               + (f"|Misses, rule only in past work: {why}" if why else ""))
        row_html.append(f"""
      <div class="row" tabindex="0" data-tip="{tip}">
        <div class="rank">{i}</div>
        <div class="who"><span class="name">{escape(r['name'])}</span><span class="lab">{escape(r['lab'])}</span>{why_html}</div>
        <div class="plot">
          <div class="gridlines">{grid}</div>
          <div class="track"></div>
          <div class="ci" style="left:{h['lo']*100:.2f}%;width:{(h['hi']-h['lo'])*100:.2f}%"></div>
          <div class="bar" style="width:{max(h['p']*100, 0.6):.2f}%"></div>
          <div class="dot" style="left:{w['p']*100:.2f}%" aria-hidden="true"></div>
        </div>
        <div class="score"><span class="big">{pct(h['p'])}</span><span class="pm">{h['k']}/{h['n']}</span></div>
        <div class="score written">{pct(w['p'])}<span class="pm">{w['k']}/{w['n']}</span></div>
      </div>""")
    table_rows = "".join(
        f"<tr><td>{escape(r['name'])}</td><td>{r['hidden']['k']}/{r['hidden']['n']}</td>"
        f"<td>{pct(r['hidden']['p'])}</td><td>{pct(r['hidden']['lo'])} to {pct(r['hidden']['hi'])}</td>"
        f"<td>{r['written']['k']}/{r['written']['n']}</td><td>{pct(r['written']['p'])}</td>"
        f"<td>{', '.join(f'{KIND_TEXT[k]} ({c})' for k, c in r['hidden']['fails'].items())}</td></tr>"
        for r in rows)
    ticks = "".join(f'<span style="left:{t}%">{t}%</span>' for t in range(0, 101, 20))

    return f"""<!doctype html>
<html lang="en" class="viz-root">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PrecedentBench leaderboard</title>
<style>
.viz-root {{
  color-scheme: light;
  --surface-1: #fcfcfb; --surface-2: #f3f2ef; --grid: #e6e5e1;
  --text-primary: #0b0b0b; --text-secondary: #52514e; --text-muted: #7a7974;
  --series-1: #2a78d6; --series-1-wash: rgba(42,120,214,.28);
  --series-2: #0b0b0b;
}}
@media (prefers-color-scheme: dark) {{
  :root:where(:not([data-theme="light"])).viz-root {{
    color-scheme: dark;
    --surface-1: #1a1a19; --surface-2: #232321; --grid: #33332f;
    --text-primary: #f0efec; --text-secondary: #c3c2b7; --text-muted: #8e8d86;
    --series-1: #3987e5; --series-1-wash: rgba(57,135,229,.38);
    --series-2: #f0efec;
  }}
}}
:root[data-theme="dark"].viz-root {{
  color-scheme: dark;
  --surface-1: #1a1a19; --surface-2: #232321; --grid: #33332f;
  --text-primary: #f0efec; --text-secondary: #c3c2b7; --text-muted: #8e8d86;
  --series-1: #3987e5; --series-1-wash: rgba(57,135,229,.38);
  --series-2: #f0efec;
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--surface-1); color: var(--text-primary);
  font: 15px/1.45 ui-sans-serif, -apple-system, "Segoe UI", Inter, Helvetica, Arial, sans-serif; }}
.page {{ max-width: 1000px; margin: 0 auto; padding: 48px 28px 56px; }}
.eyebrow {{ color: var(--text-muted); font-size: 13px; letter-spacing: .04em; text-transform: uppercase; margin: 0 0 8px; }}
h1 {{ font-size: 34px; line-height: 1.15; margin: 0 0 10px; font-weight: 650; letter-spacing: -.01em; }}
.lede {{ color: var(--text-secondary); margin: 0 0 28px; max-width: 720px; }}
.controls {{ display: flex; gap: 18px; align-items: center; justify-content: space-between; flex-wrap: wrap;
  border-top: 1px solid var(--grid); padding: 14px 0 6px; }}
.legend {{ display: flex; gap: 20px; flex-wrap: wrap; color: var(--text-secondary); font-size: 13px; }}
.legend span {{ display: inline-flex; align-items: center; gap: 8px; }}
.key-bar {{ width: 22px; height: 10px; border-radius: 0 3px 3px 0; background: var(--series-1); }}
.key-ci {{ width: 22px; height: 4px; border-radius: 2px; background: var(--series-1-wash); }}
.key-dot {{ width: 10px; height: 10px; border-radius: 50%; background: var(--surface-1);
  border: 2px solid var(--series-2); }}
.toggle button {{ font: inherit; font-size: 13px; color: var(--text-secondary); background: none;
  border: 1px solid var(--grid); padding: 5px 12px; cursor: pointer; }}
.toggle button:first-child {{ border-radius: 6px 0 0 6px; }}
.toggle button:last-child {{ border-radius: 0 6px 6px 0; border-left: 0; }}
.toggle button[aria-pressed="true"] {{ background: var(--surface-2); color: var(--text-primary); }}
.head, .row {{ display: grid; grid-template-columns: 28px 250px 1fr 76px 76px; align-items: center; gap: 14px; }}
.head {{ color: var(--text-muted); font-size: 12px; padding: 14px 0 6px; }}
.head .axis {{ position: relative; height: 16px; }}
.head .axis span {{ position: absolute; transform: translateX(-50%); }}
.head .axis span:first-child {{ transform: none; }}
.head .axis span:last-child {{ transform: translateX(-100%); }}
.head .r {{ text-align: right; }}
.row {{ padding: 12px 0; border-top: 1px solid var(--grid); outline: none; }}
.row:hover, .row:focus-visible {{ background: var(--surface-2); }}
.rank {{ color: var(--text-muted); font-variant-numeric: tabular-nums; text-align: right; }}
.who {{ display: flex; flex-direction: column; }}
.name {{ font-weight: 600; }}
.lab {{ color: var(--text-muted); font-size: 12px; }}
.why {{ color: var(--text-secondary); font-size: 12px; margin-top: 2px; }}
.plot {{ position: relative; height: 28px; }}
.plot .gridlines i {{ position: absolute; top: 0; bottom: 0; width: 1px; background: var(--grid); }}
.track {{ position: absolute; inset: 0; background-image: linear-gradient(var(--grid), var(--grid));
  background-size: 1px 100%; background-repeat: no-repeat; }}
.ci {{ position: absolute; top: 12px; height: 4px; background: var(--series-1-wash); border-radius: 2px; }}
.bar {{ position: absolute; left: 0; top: 7px; height: 14px; background: var(--series-1); border-radius: 0 4px 4px 0; }}
.dot {{ position: absolute; top: 50%; width: 12px; height: 12px; margin: -6px 0 0 -6px; border-radius: 50%;
  background: var(--surface-1); border: 2px solid var(--series-2); box-shadow: 0 0 0 2px var(--surface-1); }}
.score {{ text-align: right; font-variant-numeric: tabular-nums; display: flex; flex-direction: column; }}
.score .big {{ font-size: 20px; font-weight: 650; }}
.score .pm {{ color: var(--text-muted); font-size: 12px; }}
.score.written {{ color: var(--text-secondary); font-size: 16px; }}
table {{ width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; margin-top: 10px; }}
th, td {{ text-align: left; padding: 10px 8px; border-top: 1px solid var(--grid); }}
th {{ color: var(--text-muted); font-weight: 500; font-size: 12px; }}
[hidden] {{ display: none !important; }}
.tip {{ position: fixed; pointer-events: none; background: var(--text-primary); color: var(--surface-1);
  font-size: 13px; padding: 9px 11px; border-radius: 8px; max-width: 320px; line-height: 1.4; z-index: 9; }}
.tip b {{ display: block; margin-bottom: 3px; }}
.method {{ margin-top: 34px; color: var(--text-secondary); font-size: 13px; border-top: 1px solid var(--grid);
  padding-top: 16px; display: grid; gap: 6px; }}
.method b {{ color: var(--text-primary); font-weight: 600; }}
@media (max-width: 720px) {{
  .head, .row {{ grid-template-columns: 22px 1fr 60px 60px; }}
  .plot, .head .axis {{ grid-column: 1 / -1; grid-row: 2; }}
}}
</style>
</head>
<body>
<div class="page">
  <p class="eyebrow">PrecedentBench · Vals Hacks 2026</p>
  <h1>Can AI agents follow the rules nobody wrote down?</h1>
  <p class="lede">Each agent joins the finance team at a simulated AI company, gets five new supplier
  invoices and three months of company email, Slack and tickets. Which invoices need the finance director's
  approval was never written down: the cutoff moved from $5,000 to $10,000 in October, and one supplier stopped
  needing approval after signing a contract. The only way to know is to read how the team actually worked.</p>

  <div class="controls">
    <div class="legend" aria-label="Legend">
      <span><i class="key-bar"></i>Pass rate, rule only in past work</span>
      <span><i class="key-ci"></i>95% range</span>
      <span><i class="key-dot"></i>Pass rate, same rule written in an email</span>
    </div>
    <div class="toggle" role="group" aria-label="View">
      <button aria-pressed="true" data-view="chart">Chart</button><button aria-pressed="false" data-view="table">Table</button>
    </div>
  </div>

  <section id="chart">
    <div class="head">
      <div></div><div>Model</div>
      <div class="axis">{ticks}</div>
      <div class="r">Unwritten</div><div class="r">Written</div>
    </div>
    {''.join(row_html)}
  </section>

  <section id="table" hidden>
    <table>
      <thead><tr><th>Model</th><th>Unwritten, passed</th><th>Unwritten, rate</th><th>95% range</th>
      <th>Written, passed</th><th>Written, rate</th><th>How it missed (unwritten)</th></tr></thead>
      <tbody>{table_rows}</tbody>
    </table>
  </section>

  <div class="method">
    <div><b>Pass</b> means every check holds: the one invoice that needs approval goes to the director, the four
    that don't are logged and she isn't bothered about them, and past records are left untouched.</div>
    <div><b>Attempts:</b> {n_txt} per model per version, each in a fresh sandbox. Range is a 95% Wilson
    interval on the pass rate, wide because the number of attempts is small.</div>
    <div><b>Written version</b> is the same company with three extra emails from the director stating the rules.
    It checks the task is fair: a model that fails here is not failing because the rule is hidden.</div>
    <div><b>Agents:</b> Claude models run in Claude Code, GPT models run in Codex, on Valkyrie with Modal sandboxes.
    Company background: Redwood Inference corpus (EnterpriseRAG-Bench, Onyx, MIT).</div>
  </div>
</div>
<div class="tip" hidden></div>
<script>
const t = new URLSearchParams(location.search).get("theme");
if (t) document.documentElement.dataset.theme = t;
const tip = document.querySelector('.tip');
document.querySelectorAll('.row').forEach(row => {{
  const show = (x, y) => {{
    const [title, ...lines] = row.dataset.tip.split('|');
    tip.innerHTML = '<b>' + title + '</b>' + lines.join('<br>');
    tip.hidden = false;
    const w = tip.offsetWidth;
    tip.style.left = Math.min(x + 14, innerWidth - w - 8) + 'px';
    tip.style.top = (y + 14) + 'px';
  }};
  row.addEventListener('mousemove', e => show(e.clientX, e.clientY));
  row.addEventListener('mouseleave', () => tip.hidden = true);
  row.addEventListener('focus', () => {{ const r = row.getBoundingClientRect(); show(r.left + 240, r.top); }});
  row.addEventListener('blur', () => tip.hidden = true);
}});
document.querySelectorAll('.toggle button').forEach(b => b.addEventListener('click', () => {{
  document.querySelectorAll('.toggle button').forEach(x => x.setAttribute('aria-pressed', x === b));
  document.getElementById('chart').hidden = b.dataset.view !== 'chart';
  document.getElementById('table').hidden = b.dataset.view !== 'table';
}}));
</script>
</body>
</html>
"""


if __name__ == "__main__":
    rows = summarize(json.loads((HERE / "v3_attempts.json").read_text()))
    (HERE / "leaderboard.html").write_text(render(rows))
    for r in rows:
        print(f"{r['name']:20s} unwritten {r['hidden']['k']}/{r['hidden']['n']}  written {r['written']['k']}/{r['written']['n']}")
