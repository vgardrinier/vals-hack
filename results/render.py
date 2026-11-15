"""Render the PrecedentBench page (messy monday v3) into results/leaderboard.html.

    python3 results/render.py

Layout follows the team's implicit-action-bench page (nav, hero, stats, intro, ranking card with a
score toggle, chart card, insights + big-number card, tabbed results, trajectory cards, methodology).
Every number on the page is computed here from:
  results/morning_v3.json      per-try results of the v3 run (shared plain agent)
  results/baselines_v3.json    scripted no-AI strategies graded by the same check.py
  results/morning_round2.json  earlier round, shared agent (for the own-agent comparison)
  results/morning_vendor.json  earlier round, each brand's own agent (Claude Code / Codex)
  results/examples_v3.json     hand-picked trajectories with run links (written after reading runs)

Pass@1 = share of tries with all 15 invoices right. Mean score = share of invoices right per try.
"""

from __future__ import annotations

import json
import math
import random
import re
from collections import defaultdict
from html import escape
from pathlib import Path

HERE = Path(__file__).parent
MODELS = {
    "claude-fable-5-2": ("Claude Fable 5.2", "anthropic"),
    "claude-opus-5-5": ("Claude Opus 5.5", "anthropic"),
    "claude-sonnet-5-5": ("Claude Sonnet 5.5", "anthropic"),
    "gpt-6.1-sol": ("GPT-6.1 Sol", "openai"),
    "gpt-6-astra": ("GPT-6 Astra", "openai"),
}
LAB = {"anthropic": "Anthropic", "openai": "OpenAI"}
ICON = {k: (HERE / "icons" / f"{k}.svg").read_text() for k in ("anthropic", "openai")}
DOSES = [2, 3, 5]


def load(name: str):
    p = HERE / name
    return json.loads(p.read_text()) if p.exists() else []


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = k / n
    den = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, mid - half), min(1.0, mid + half)


def boot(xs: list[float], reps: int = 4000) -> tuple[float, float]:
    if not xs:
        return 0.0, 0.0
    rng = random.Random(0)
    ms = sorted(sum(rng.choice(xs) for _ in xs) / len(xs) for _ in range(reps))
    return ms[int(.025 * reps)], ms[int(.975 * reps) - 1]


def scored(a: dict) -> bool:
    return a.get("status") == "FINISHED" and a.get("reward") is not None


LEVELS = [("L1", "4 habits"), ("L2", "8 habits"), ("L3", "8 habits + old policy doc")]


def level(a: dict) -> str | None:
    v = a.get("version", "")
    if v.startswith("morningL2-"):
        return "TOLD" if v.endswith("-told") else ("L3" if a.get("handbook") else "L2")
    if v.startswith("morning3-") and not a.get("handbook") and not a.get("told") and a.get("dose") in (3, 5):
        return "L1"
    return None


def habit_buckets(a: dict) -> dict[str, list[bool]]:
    """Per invoice of the 8-habit batch: which kind of habit it tests, and whether the try got it right."""
    res = defaultdict(list)
    for l in a.get("checks", []):
        m = re.match(r"(PASS|FAIL) (\S+) \(([^,]+), \$([\d,\.]+)\)(.*)", l)
        if not m:
            continue
        ok, vendor, amount, rest = m.group(1) == "PASS", m.group(3), float(m.group(4).replace(",", "")), m.group(5)
        note_ok = ok or ("note" not in rest and "logged" not in rest)
        cc_ok = ok or ("cost center" not in rest and "logged" not in rest)
        if vendor in ("Wrenfield",):
            res["changed"].append(cc_ok)
        elif vendor in ("Halverson", "Kellerby", "Pellham"):
            res["changed"].append(note_ok)                    # contract, card since Oct 19
        elif vendor == "Marrow":
            res["changed"].append(note_ok)                    # cutoff moved
        elif vendor == "Calloway" or (vendor == "Ironwood" and amount > 10000):
            res["team"].append(note_ok)                       # who reviews / Security kept the old cutoff
        elif vendor == "Selbourne":
            (res["team"] if amount > 10000 else res["two"]).append(ok)   # Recruiting vs People, plus reviewer
        elif vendor in ("Quillmark", "Ironwood", "Vantor"):
            res["two"].append(note_ok)                        # PO matched on unreviewed Infra; re-sent duplicate
        else:
            res["routine"].append(ok)
    return res


def stats(xs: list[dict]) -> dict:
    n = len(xs)
    k = sum(1 for a in xs if a["reward"] >= 0.9999)
    means = [a["reward"] for a in xs]
    lo, hi = wilson(k, n)
    mlo, mhi = boot(means)
    return {"n": n, "k": k, "pass": k / n if n else 0, "pass_lo": lo, "pass_hi": hi,
            "mean": sum(means) / n if n else 0, "mean_lo": mlo, "mean_hi": mhi}


def build_data() -> dict:
    allv = [a for a in load("morning_v3.json") if scored(a)]
    out = {"models": [], "levels": LEVELS}
    for mid, (name, lab) in MODELS.items():
        xs = [dict(a, level=level(a)) for a in allv if a["model"] == mid]
        if not xs:
            continue
        by = lambda lv, d=None: [a for a in xs if a["level"] == lv and (d is None or a.get("dose") == d)]
        lvl = {lv: {"all": stats(by(lv)), 3: stats(by(lv, 3)), 5: stats(by(lv, 5))} for lv, _ in LEVELS}
        hb = defaultdict(list)
        for a in by("L2"):
            for kk, v in habit_buckets(a).items():
                hb[kk] += v
        extra = {   # 4-habit side versions: dated doc and told control
            "l1_doc": stats([a for a in xs if a.get("version", "").startswith("morning3-") and a.get("handbook")]),
            "l1_told": stats([a for a in xs if a.get("version", "").startswith("morning3-") and a.get("told")]),
        }
        out["models"].append({
            "id": mid, "name": name, "lab": lab, "levels": lvl,
            "main": stats(by("L1", 5) + by("L2", 5) + by("L3", 5)),
            "told": stats(by("TOLD")), "habits": {kk: sum(v) / len(v) for kk, v in hb.items() if v}, **extra,
        })
    out["models"].sort(key=lambda m: (-m["main"]["pass"], -m["main"]["mean"]))
    out["baselines"] = load("baselines_v3.json")
    names = sorted({b["strategy"] for b in out["baselines"]})
    out["baseline_summary"] = []
    for s_ in names:
        rs = [b for b in out["baselines"] if b["strategy"] == s_ and b.get("level") in ("L1", "L2", "L3") and b.get("dose") == 5]
        if not rs:
            continue
        out["baseline_summary"].append({"name": s_, "pass": sum(b["score"] >= .9999 for b in rs) / len(rs),
                                        "mean": sum(b["score"] for b in rs) / len(rs),
                                        "by": {lv: sum(b["score"] >= .9999 for b in rs if b["level"] == lv) / max(1, len([b for b in rs if b["level"] == lv])) for lv, _ in LEVELS}})
    r2 = [a for a in load("morning_round2.json") if scored(a)]
    ven = [a for a in load("morning_vendor.json") if scored(a)]
    out["vendor"] = []
    for mid, (name, lab) in MODELS.items():
        a, b = [x for x in r2 if x["model"] == mid], [x for x in ven if x["model"] == mid]
        if a and b:
            out["vendor"].append({"name": name, "shared": stats(a), "own": stats(b),
                                  "agent": "Claude Code" if lab == "anthropic" else "Codex"})
    out["examples"] = load("examples_v3.json")
    out["n_tries"] = max((m["main"]["n"] for m in out["models"]), default=0)
    return out


def pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def page(d: dict) -> str:
    ms = d["models"]
    if not ms:
        raise SystemExit("no results yet")
    best = ms[0]
    l2 = sorted(ms, key=lambda m: -m["levels"]["L2"][5]["pass"])
    l3 = sorted(ms, key=lambda m: -m["levels"]["L3"][5]["pass"])
    told_k, told_n = sum(m["told"]["k"] for m in ms), sum(m["told"]["n"] for m in ms)
    small = [m for m in ms if m["id"] in ("claude-sonnet-5-5", "claude-opus-5-5")]
    copy = next((b for b in d["baseline_summary"] if "same size" in b["name"]), None)
    dumb = max((b["pass"] for b in d["baseline_summary"] if "same size" not in b["name"]), default=0)
    hard = (f"Yes, once the work looks like a real team's. With 4 habits the best agents get the whole job right most of the time; "
            f"with 8 habits at once the best ({l2[0]['name']}) manages {pct(l2[0]['levels']['L2'][5]['pass'])}, "
            f"and with last year's policy doc added, {pct(l3[0]['levels']['L3'][5]['pass'])}. "
            + ", ".join(f"{m['name'].split(' ', 1)[1]} {pct(m['levels']['L2'][5]['pass'])}" for m in small) + " on 8 habits.")
    fair = (f"Yes. Every habit is shown by 5 recent examples in the history. Told the 8 habits in plain words, agents get "
            f"{told_k} of {told_n} tries fully right. Same plain agent for every model. Brainless scripts get {pct(dumb)} fully right; "
            f"a 'copy the latest invoice from the same supplier and size' lookup gets {pct(copy['pass']) if copy else 'n/a'}.")
    blob = json.dumps({**d, "icons": ICON})
    return (TEMPLATE.replace("__DATA__", blob)
            .replace("__HARD__", escape(hard)).replace("__FAIR__", escape(fair))
            .replace("__N_MODELS__", str(len(ms))).replace("__N_TRIES__", str(d["n_tries"]))
            .replace("__BEST__", pct(best["main"]["pass"])).replace("__L2_BEST__", pct(l2[0]["levels"]["L2"][5]["pass"]))
            .replace("__DOC_BEST__", pct(l3[0]["levels"]["L3"][5]["pass"]))
            .replace("__BEST_NAME__", escape(best["name"])))


TEMPLATE = r"""<!doctype html>
<html lang="en" class="viz-root">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PrecedentBench: the habits nobody wrote down</title>
<style>
.viz-root {
  color-scheme: light;
  --surface-1:#FFFFFF; --surface-2:#F7F8FA; --card:#FFFFFF; --line:#E5E7EB; --track:#F1F5F9;
  --text-primary:#111827; --text-secondary:#475569; --text-muted:#94A3B8; --accent:#4F46E5;
  --anthropic-a:#FED7C3; --anthropic-b:#F28C5C; --anthropic-c:#B9522B;
  --openai-a:#A7E3CF; --openai-b:#38A77C; --openai-c:#147A59;
  --base:#CBD5E1; --success:#147A59; --warning:#B7791F; --danger:#C2413B; --quote-bg:#111827; --quote-ink:#F8FAFC;
  --s1:#2a78d6; --s2:#eb6834; --s3:#1baf7a; --s4:#eda100; --s5:#e87ba4;
}
:root[data-theme="dark"].viz-root {
  color-scheme: dark;
  --surface-1:#0F1115; --surface-2:#171A20; --card:#14171C; --line:#272B33; --track:#1E2229;
  --text-primary:#F1F5F9; --text-secondary:#B6C0CD; --text-muted:#7B8696; --accent:#8B85F0;
  --anthropic-a:#7A3518; --anthropic-b:#D96A3A; --anthropic-c:#F3A27B;
  --openai-a:#0F5A41; --openai-b:#2E9E72; --openai-c:#6FD3AE;
  --base:#475569; --quote-bg:#1E2230;
  --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#c98500; --s5:#d55181;
}
* { box-sizing:border-box; }
html { scroll-behavior:smooth; overflow-x:hidden; }
body { margin:0; background:var(--surface-1); color:var(--text-primary); font:15px/1.55 Inter,ui-sans-serif,-apple-system,"Segoe UI",Helvetica,Arial,sans-serif; -webkit-font-smoothing:antialiased; }
a { color:inherit; }
.mono { font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace; font-variant-numeric:tabular-nums; }
.wrap { max-width:1380px; margin:0 auto; padding:0 56px; }
nav.top { border-bottom:1px solid var(--line); position:sticky; top:0; z-index:5; background:color-mix(in srgb,var(--surface-1) 92%,transparent); backdrop-filter:blur(12px); }
nav.top .wrap { display:flex; align-items:center; min-height:64px; gap:36px; }
.brand { display:flex; align-items:center; gap:9px; font-weight:650; font-size:16px; text-decoration:none; }
.brand-mark { width:22px; height:22px; border-radius:6px; background:linear-gradient(135deg,#A5B4FC,var(--accent)); }
.navlinks { display:flex; gap:30px; font-size:14px; }
.navlinks a { text-decoration:none; }
.navright { margin-left:auto; font-size:13px; border:1px solid var(--line); border-radius:6px; padding:7px 16px; text-decoration:none; }
.crumbs { font-size:12px; color:var(--text-muted); padding:14px 0; }
.crumbs b { color:var(--text-primary); font-weight:500; }
.hero { text-align:center; padding:54px 0 40px; }
.hero h1 { font-size:56px; line-height:1.06; font-weight:450; letter-spacing:-.035em; margin:0 0 18px; }
.hero .with { color:var(--text-muted); font-size:13px; margin-bottom:22px; display:flex; gap:8px; justify-content:center; align-items:baseline; flex-wrap:wrap; }
.hero .with b { color:var(--text-primary); font-size:17px; font-weight:650; }
.hero p { color:var(--text-secondary); max-width:760px; margin:0 auto 26px; font-size:16px; }
.buttons { display:flex; gap:10px; justify-content:center; }
.button { font-size:13px; padding:9px 18px; border-radius:6px; text-decoration:none; background:var(--surface-2); border:1px solid var(--line); }
.button.primary { background:var(--accent); color:#fff; border-color:var(--accent); font-weight:550; }
.stats { display:grid; grid-template-columns:repeat(4,1fr); padding:28px 0 46px; }
.stat { text-align:center; border-left:1px solid var(--line); padding:6px 0; }
.stat:first-child { border-left:0; }
.stat .value { font-size:44px; font-weight:400; letter-spacing:-.03em; line-height:1.15; }
.stat .key { color:var(--text-muted); font-size:16px; }
.answers { display:grid; grid-template-columns:1fr 1fr; gap:18px; padding-bottom:84px; }
.answer { border:1px solid var(--line); border-radius:12px; padding:22px 24px; background:var(--surface-2); }
.answer .q { font-size:12px; text-transform:uppercase; letter-spacing:.1em; color:var(--accent); font-weight:650; }
.answer p { margin:8px 0 0; font-size:15.5px; color:var(--text-primary); }
.leaderboard { padding-bottom:100px; }
.leaderboard-intro { display:grid; grid-template-columns:minmax(250px,.72fr) minmax(0,1.28fr); gap:80px; align-items:start; margin-bottom:34px; }
.section-kicker { color:var(--accent); font-size:11px; font-weight:650; text-transform:uppercase; letter-spacing:.12em; margin-bottom:10px; }
.leaderboard-intro h2 { font-size:34px; line-height:1.13; letter-spacing:-.025em; margin:0; }
.leaderboard-body { display:grid; grid-template-columns:1fr 1fr; gap:26px 42px; }
.leaderboard-body p { color:var(--text-secondary); margin:0; }
.leaderboard-body .chips { grid-column:1 / -1; }
h2 { font-size:21px; font-weight:500; margin:0 0 22px; letter-spacing:-.01em; }
.chips { display:flex; gap:8px; flex-wrap:wrap; }
.chips a { font-size:13px; background:var(--surface-2); border-radius:6px; padding:6px 12px; text-decoration:none; }
.card { background:var(--card); border:1px solid var(--line); border-radius:14px; padding:32px 38px 34px; box-shadow:0 14px 44px rgba(15,23,42,.055); }
.ranking-card { margin-bottom:24px; }
.plot-card { max-width:1040px; margin:0 auto; }
.control-bar { display:flex; align-items:flex-end; justify-content:space-between; gap:16px; padding-bottom:22px; margin-bottom:8px; border-bottom:1px solid var(--line); }
.control-group > span { display:block; color:var(--text-muted); font-size:11px; text-transform:uppercase; letter-spacing:.07em; margin-bottom:7px; }
.segmented { display:inline-flex; padding:3px; gap:2px; border-radius:7px; background:var(--surface-2); border:1px solid var(--line); }
.segmented button { border:0; border-radius:5px; background:transparent; color:var(--text-secondary); font:inherit; font-size:12px; padding:6px 9px; cursor:pointer; }
.segmented button[aria-pressed="true"] { background:var(--card); color:var(--text-primary); box-shadow:0 1px 4px rgba(0,0,0,.08); }
.card-head { color:var(--text-muted); font-size:12px; margin:18px 0 5px; }
.leader-columns, .leader-top { display:grid; grid-template-columns:minmax(170px,1fr) 150px 120px; gap:12px; align-items:center; }
.leader-columns span:not(:first-child) { text-align:right; }
.leader-row { padding:13px 10px 12px; margin:0 -10px; border-radius:8px; outline:none; }
.leader-row:hover, .leader-row:focus-visible { background:var(--surface-2); }
.leader-row.baseline .model-name { color:var(--text-secondary); font-weight:400; font-size:14px; }
.model-name { font-size:16px; font-weight:500; display:flex; align-items:center; gap:7px; min-width:0; }
.model-name svg { width:16px; height:16px; fill:currentColor; flex:none; }
.model-tag { color:var(--text-muted); font-size:12.5px; font-weight:400; white-space:nowrap; }
.model-score, .model-metric { font-size:13px; white-space:nowrap; text-align:right; }
.model-score small, .model-metric small { color:var(--text-muted); font-size:11.5px; margin-left:6px; }
.leader-bar { position:relative; height:6px; margin-top:10px; background:var(--track); border-radius:3px; overflow:hidden; }
.leader-fill { position:absolute; inset:0 auto 0 0; border-radius:3px; }
.base-divider { color:var(--text-muted); font-size:11px; text-transform:uppercase; letter-spacing:.08em; margin:18px 0 2px; padding-top:14px; border-top:1px dashed var(--line); }
.axis { position:relative; height:24px; margin-top:26px; border-top:1px solid var(--line); }
.axis span { position:absolute; top:9px; transform:translateX(-50%); color:var(--text-muted); font-size:12px; }
.axis span:first-child { transform:none; }
.axis span:last-child { transform:translateX(-100%); }
.card-foot { display:flex; justify-content:space-between; align-items:center; margin-top:24px; gap:12px; color:var(--text-muted); font-size:12px; }
.plot-head { display:flex; justify-content:space-between; gap:24px; align-items:flex-end; margin-bottom:16px; }
.plot-head b { font-size:18px; font-weight:520; }
.plot-head .sub2 { display:block; color:var(--text-muted); font-size:12px; margin-top:4px; }
svg.curve { width:100%; height:360px; overflow:visible; }
svg.curve text { fill:var(--text-muted); font-size:11px; }
svg.curve .grid { stroke:var(--line); stroke-width:1; }
svg.curve .lbl { fill:var(--text-primary); font-size:12px; }
.legend { display:flex; gap:16px; flex-wrap:wrap; font-size:12.5px; color:var(--text-secondary); margin-top:12px; }
.legend i { display:inline-block; width:14px; height:3px; border-radius:2px; margin-right:6px; vertical-align:middle; }
.takeaway-layout { display:grid; grid-template-columns:1.15fr .85fr; gap:56px; align-items:start; padding:90px 0 100px; }
.takeaways { list-style:none; padding:0; margin:0; counter-reset:t; }
.takeaways li { counter-increment:t; padding:18px 0 18px 30px; border-bottom:1px solid var(--line); position:relative; }
.takeaways li::before { content:counter(t); position:absolute; left:8px; top:18px; color:var(--accent); }
.takeaways b { display:block; font-weight:500; font-size:16px; margin-bottom:4px; }
.takeaways span { color:var(--text-secondary); font-size:13.5px; }
.quote { background:var(--quote-bg); color:var(--quote-ink); border-radius:10px; padding:34px 32px; margin-top:40px; }
.quote strong { display:block; font-size:46px; line-height:1; font-weight:450; letter-spacing:-.04em; }
.quote p { font-size:18px; line-height:1.45; margin:16px 0 0; }
.quote .who { margin-top:22px; font-size:13px; opacity:.7; }
.section { padding:0 0 96px; }
.sub { color:var(--text-secondary); margin:-10px 0 26px; max-width:760px; }
.tabs { display:flex; gap:26px; border-bottom:1px solid var(--line); margin-bottom:30px; overflow-x:auto; }
.tabs button { font:inherit; font-size:14px; background:none; border:0; padding:0 0 10px; color:var(--text-secondary); cursor:pointer; border-bottom:2px solid transparent; margin-bottom:-1px; white-space:nowrap; }
.tabs button[aria-selected="true"] { color:var(--accent); border-bottom-color:var(--accent); }
.plain { width:100%; border-collapse:collapse; font-size:14px; }
.plain th, .plain td { text-align:left; padding:11px 8px; border-bottom:1px solid var(--line); vertical-align:middle; }
.plain th { color:var(--text-muted); font-weight:400; font-size:12.5px; }
.plain td.score, .plain th.score { text-align:right; }
.plain td small { color:var(--text-muted); display:block; font-size:12px; }
.score-pill { display:inline-flex; justify-content:center; min-width:58px; padding:5px 8px; border-radius:5px; font-size:12px; }
.score-high { background:color-mix(in srgb,var(--success) 14%,var(--surface-1)); color:var(--success); }
.score-mid { background:color-mix(in srgb,var(--warning) 14%,var(--surface-1)); color:var(--warning); }
.score-low { background:color-mix(in srgb,var(--danger) 12%,var(--surface-1)); color:var(--danger); }
.trajectory-list { display:grid; gap:14px; }
.trajectory { border:1px solid var(--line); border-radius:10px; padding:22px; display:grid; grid-template-columns:200px 1fr; gap:26px; }
.trajectory .eyebrow { color:var(--text-muted); font-size:11px; text-transform:uppercase; letter-spacing:.08em; }
.trajectory h3 { font-size:17px; font-weight:550; margin:5px 0 8px; }
.trajectory p { color:var(--text-secondary); margin:0 0 10px; }
.trajectory blockquote { margin:0 0 10px; padding-left:12px; border-left:3px solid var(--line); color:var(--text-primary); font-size:14px; }
.trajectory code { color:var(--text-muted); font-size:11px; overflow-wrap:anywhere; }
.fair { display:grid; grid-template-columns:repeat(3,1fr); gap:14px; }
.fair div { border:1px solid var(--line); border-radius:10px; padding:16px 18px; }
.fair b { display:block; font-weight:550; margin-bottom:4px; }
.fair span { color:var(--text-secondary); font-size:13.5px; }
.method { color:var(--text-secondary); font-size:14px; max-width:880px; }
.method p { margin:0 0 14px; }
.method b { color:var(--text-primary); font-weight:500; }
.method-callout { border-left:3px solid var(--accent); padding:12px 16px; background:var(--surface-2); border-radius:0 7px 7px 0; margin:24px 0; }
footer { border-top:1px solid var(--line); color:var(--text-muted); font-size:12px; padding:22px 0 40px; }
.tip { position:fixed; pointer-events:none; background:var(--text-primary); color:var(--surface-1); font-size:12.5px; padding:10px 12px; border-radius:10px; max-width:340px; line-height:1.45; z-index:9; }
.tip b { display:block; margin-bottom:3px; }
[hidden] { display:none !important; }
@media (max-width:920px) {
  .takeaway-layout, .leaderboard-intro, .leaderboard-body, .answers, .fair { grid-template-columns:1fr; }
  .stats { grid-template-columns:repeat(2,1fr); row-gap:24px; }
  .hero h1 { font-size:36px; }
  .navlinks { display:none; }
  .wrap { padding:0 22px; }
  .trajectory { grid-template-columns:1fr; gap:10px; }
}
</style>
</head>
<body>
<nav class="top"><div class="wrap">
  <a class="brand" href="#"><span class="brand-mark"></span>PrecedentBench</a>
  <div class="navlinks"><a href="#leaderboard">Leaderboard</a><a href="#results">Results</a><a href="#trajectories">Trajectories</a><a href="#method">Methodology</a><a href="#takeaways">Takeaways</a></div>
  <a class="navright" href="#method">Vals Hacks 2026</a>
</div></nav>
<div class="wrap">
  <div class="crumbs">Home <span>›</span> Benchmarks <span>›</span> <b>PrecedentBench</b></div>

  <section class="hero">
    <h1>The benchmark for the habits<br>nobody wrote down.</h1>
    <div class="with">Built on <b>Valkyrie</b> · <b>one plain agent for every model</b> <span>by Yaya &amp; Vivi team</span></div>
    <p>Most of what a company knows lives in how people did things before, not in a handbook. PrecedentBench gives
    an agent a finance team's history and a normal Monday of invoices, and checks whether it logs them the way the team
    actually works now.</p>
    <div class="buttons"><a class="button primary" href="#leaderboard">Explore leaderboard</a><a class="button" href="#method">Read methodology</a></div>
  </section>

  <section class="stats">
    <div class="stat"><div class="value">__N_MODELS__</div><div class="key">frontier models</div></div>
    <div class="stat"><div class="value">8</div><div class="key">habits, nobody wrote down</div></div>
    <div class="stat"><div class="value">__BEST__</div><div class="key">best whole-job pass rate</div></div>
    <div class="stat"><div class="value">__L2_BEST__</div><div class="key">best, with all 8 habits at once</div></div>
  </section>

  <section class="answers">
    <div class="answer"><div class="q">Is it hard?</div><p>__HARD__</p></div>
    <div class="answer"><div class="q">Is it fair?</div><p>__FAIR__</p></div>
  </section>

  <section class="leaderboard" id="leaderboard">
    <div class="leaderboard-intro">
      <div><div class="section-kicker">Company knowledge</div><h2>The PrecedentBench leaderboard</h2></div>
      <div class="leaderboard-body">
        <p>The agent joins Redwood Inference's finance team on a Monday. Fifteen supplier invoices are in the inbox,
        and the workspace holds three quarters of invoice history, about 2,500 emails, Slack threads and tickets.
        The request is one line: log the invoices.</p>
        <p>Nothing says how. The team's habits only show in the past rows. Level 1 has 4 habits; level 2 has 8 at once,
        like a real team: some changed this autumn, some depend on two conditions. Level 3 adds last year's policy doc.
        Every habit is shown by recent examples, so a careful new hire can get every invoice right.</p>
        <div class="chips"><a href="#results">Where it breaks</a><a href="#trajectories">Trajectory evidence</a><a href="#takeaways">Research insights</a></div>
      </div>
    </div>

    <div class="card ranking-card">
      <div class="control-bar">
        <div class="control-group"><span>Score view</span><div class="segmented" id="score-toggle"><button data-mode="pass" aria-pressed="true">Whole job right</button><button data-mode="mean" aria-pressed="false">Invoices right</button></div></div>
        <div class="control-group"><span>Level</span><div class="segmented" id="doc-toggle"><button data-doc="main" aria-pressed="true">All levels</button><button data-doc="L1" aria-pressed="false">4 habits</button><button data-doc="L2" aria-pressed="false">8 habits</button><button data-doc="L3" aria-pressed="false">8 + old doc</button></div></div>
      </div>
      <div class="card-head leader-columns"><span>Model</span><span id="score-head">Whole job right</span><span>Invoices right</span></div>
      <div id="rows"></div>
      <div class="axis" id="axis"></div>
      <div class="card-foot"><span>Shared plain agent, same prompt and tools for every model. Brainless scripts below the line, graded by the same checker.</span><span class="mono" id="foot-n"></span></div>
    </div>

    <div class="card plot-card">
      <div class="plot-head">
        <div><b>The complexity ladder</b><span class="sub2">Whole job right as the team's habits get more like a real company's</span></div>
        <div class="control-group"><span>Examples per habit</span><div class="segmented" id="curve-toggle"><button data-c="5" aria-pressed="true">5</button><button data-c="3" aria-pressed="false">3</button></div></div>
      </div>
      <svg class="curve" id="curve" viewBox="0 0 960 360" role="img" aria-label="Pass rate by level, one line per model"></svg>
      <div class="legend" id="legend"></div>
    </div>
  </section>

  <section class="takeaway-layout" id="takeaways">
    <div><h2>Research insights</h2><ol class="takeaways" id="insights"></ol></div>
    <div class="quote"><strong>__L2_BEST__</strong><p>Best whole-job pass rate when the team runs on 8 unwritten habits at once, each shown by 5 recent examples. With 4 habits, the same agents are near perfect.</p><div class="who">Same company, same agent, more habits</div></div>
  </section>

  <section class="section" id="results">
    <h2>Results</h2>
    <p class="sub">Where it breaks, per version, and against brainless baselines. Hover a score for detail.</p>
    <div class="tabs" role="tablist">
      <button role="tab" aria-selected="true" data-tab="t-breaks">Where it breaks</button>
      <button role="tab" aria-selected="false" data-tab="t-versions">By version</button>
      <button role="tab" aria-selected="false" data-tab="t-base">Baselines</button>
      <button role="tab" aria-selected="false" data-tab="t-vendor">Own-agent check</button>
    </div>
    <div id="t-breaks"><table class="plain" id="breaks"></table></div>
    <div id="t-versions" hidden><table class="plain" id="versions"></table></div>
    <div id="t-base" hidden><table class="plain" id="base"></table></div>
    <div id="t-vendor" hidden><p class="sub" style="margin-top:0">Earlier round of the same task family: each model in its own brand's agent (Claude Code or Codex) against our shared plain agent. Whole job right.</p><table class="plain" id="vendor"></table></div>
  </section>

  <section class="section" id="trajectories">
    <h2>Representative trajectories</h2>
    <p class="sub">Real tries from the v3 run, picked by reading the logs. What we saw, and why it matters.</p>
    <div class="trajectory-list" id="trajectory-list"></div>
  </section>

  <section class="section" id="fair">
    <h2>How we checked it's fair</h2>
    <div class="fair" id="fairbox"></div>
  </section>

  <section class="section method" id="method">
    <h2>Methodology</h2>
    <p><b>World.</b> Redwood Inference, a fake AI company built on the EnterpriseRAG-Bench corpus (Onyx, MIT): about 2,500 real-looking emails, Slack threads and tickets, plus a finance history we generate from the team's habits so it can never disagree with the answer key. Three quarterly invoice trackers (about 300 invoices), the older two archived.</p>
    <p><b>Habits.</b> Before October, every invoice over $5,000 got a REVIEW note. Since then: only invoices over $10,000 get one, naming Tomasz for Infra suppliers and Mireille for everyone else; Security kept the $5,000 cutoff; Halverson stopped needing review after its contract on November 2; Wrenfield moved from Marketing to G&amp;A on October 12. Two old rows have someone's forgotten REVIEW, and a few supplier names have typos. None of it is written anywhere.</p>
    <p><b>Levels.</b> Level 1: the 4 habits above. Level 2: 8 habits at once, adding four conventions that only show in the tracker: unreviewed Infra invoices are noted "PO matched"; Selbourne invoices over $5,000 are coded Recruiting; since October 19, small Kellerby and Pellham invoices are noted "card"; a re-sent invoice (same number and amount) is logged "DUPLICATE - do not pay". Level 3: level 2 plus last year's AP policy in the drive, dated January 2026. Each habit is shown by 3 or 5 recent examples. A told control states all 8 habits in the instruction. Fifteen new invoices per task.</p>
    <p><b>Grading.</b> Deterministic: each invoice must be logged once, with the right note (no flag, or REVIEW naming the right reviewer; wording is free, and notes like "no review needed" count as no flag) and the right cost center. Past rows must stay untouched. <b>Whole job right</b> = all 15 invoices right in a try (headline). <b>Invoices right</b> = share of the 15. Intervals: 95% Wilson for whole-job, bootstrap for invoices.</p>
    <p><b>Agent.</b> One plain loop for every model: same instructions, one tool that runs a shell command, reasoning effort high, 80 steps, no fallback model. Five tries per version per model, each in a fresh sandbox on Valkyrie and Modal.</p>
    <div class="method-callout"><b>Limits.</b> The finance history is synthetic and lives in one company and one kind of job. Five tries per version gives wide intervals: neighbours in the ranking are often statistically tied. Earlier rounds were adjusted with rules fixed before seeing results, and every round is kept in the repo's archive. On 4 habits a simple precedent lookup (latest invoice of the same supplier and size) solves almost everything; on 8 habits it no longer does. A side version with 4 habits and the dated policy doc showed that a clearly dated doc no longer fools the top models.</div>
  </section>
</div>
<footer><div class="wrap">PrecedentBench · Vals Hacks 2026 · Yaya &amp; Vivi team</div></footer>
<div class="tip" hidden></div>
<script>
const t = new URLSearchParams(location.search).get("theme"); if (t) document.documentElement.dataset.theme = t;
const D = __DATA__;
const P = x => (x * 100).toFixed(0) + "%";
const P1 = x => (x * 100).toFixed(1) + "%";
const ICON = l => D.icons[l] || "";
const COLORS = ["--s1","--s2","--s3","--s4","--s5"];
const LV = {L1: "4 habits", L2: "8 habits", L3: "8 habits + old doc"};
let mode = "pass", lev = "main", dose = 5;
const tip = document.querySelector(".tip");
function bindTips(root) {
  root.querySelectorAll("[data-tip]").forEach(el => {
    el.onmousemove = e => { const [h, ...r] = el.dataset.tip.split("|"); tip.innerHTML = "<b>" + h + "</b>" + r.join("<br>"); tip.hidden = false;
      tip.style.left = Math.min(e.clientX + 14, innerWidth - tip.offsetWidth - 8) + "px"; tip.style.top = (e.clientY + 14) + "px"; };
    el.onmouseleave = () => tip.hidden = true;
  });
}
const pick = m => lev === "main" ? m.main : m.levels[lev][5];
function rows() {
  document.getElementById("score-head").textContent = mode === "pass" ? "Whole job right" : "Invoices right";
  const list = D.models.map(m => ({m, s: pick(m)})).sort((a, b) => (mode === "pass" ? b.s.pass - a.s.pass : b.s.mean - a.s.mean) || b.s.mean - a.s.mean);
  let html = list.map(({m, s}) => {
    const v = mode === "pass" ? s.pass : s.mean, lo = mode === "pass" ? s.pass_lo : s.mean_lo, hi = mode === "pass" ? s.pass_hi : s.mean_hi;
    const tipx = `${m.name}|Whole job right: ${s.k}/${s.n} tries (${P1(s.pass)}, 95%: ${P(s.pass_lo)}-${P(s.pass_hi)})|Invoices right: ${P1(s.mean)}|4 habits ${P(m.levels.L1[5].pass)} · 8 habits ${P(m.levels.L2[5].pass)} · 8 + old doc ${P(m.levels.L3[5].pass)}`;
    return `<div class="leader-row" tabindex="0" data-tip="${tipx}"><div class="leader-top">
      <span class="model-name">${ICON(m.lab)}${m.name}<span class="model-tag">${m.lab === "anthropic" ? "Anthropic" : "OpenAI"} · effort high</span></span>
      <span class="model-score mono">${P1(v)}<small>${P(lo)}-${P(hi)}</small></span>
      <span class="model-metric mono">${P1(s.mean)}<small>${s.k}/${s.n}</small></span></div>
      <div class="leader-bar"><div class="leader-fill" style="width:${Math.max(v * 100, .6)}%;background:linear-gradient(90deg,var(--${m.lab}-a),var(--${m.lab}-b))"></div></div></div>`;
  }).join("");
  html += `<div class="base-divider">Brainless scripts, same checker</div>` + D.baseline_summary.map(b => {
    const v = mode === "pass" ? (lev === "main" ? b.pass : b.by[lev]) : b.mean;
    return `<div class="leader-row baseline"><div class="leader-top"><span class="model-name">${b.name}</span><span class="model-score mono">${P1(v)}</span><span class="model-metric mono">${P1(b.mean)}</span></div>
      <div class="leader-bar"><div class="leader-fill" style="width:${Math.max(v * 100, .6)}%;background:var(--base)"></div></div></div>`;
  }).join("");
  document.getElementById("rows").innerHTML = html;
  document.getElementById("foot-n").textContent = `${D.models[0] ? pick(D.models[0]).n : 0} tries / model · 5 examples per habit`;
  bindTips(document.getElementById("rows"));
}
document.getElementById("axis").innerHTML = [0,20,40,60,80,100].map(v => `<span style="left:${v}%">${v}%</span>`).join("");
function curve() {
  const svg = document.getElementById("curve"), W = 960, H = 360, L = 60, R = 160, T = 16, B = 40;
  const xs = ["L1", "L2", "L3"], X = i => L + i * (W - L - R) / 2, Y = v => T + (1 - v) * (H - T - B);
  let s = [0, .25, .5, .75, 1].map(v => `<line class="grid" x1="${L}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}"/><text x="${L - 10}" y="${Y(v) + 4}" text-anchor="end">${v * 100}%</text>`).join("");
  s += xs.map((k, i) => `<text x="${X(i)}" y="${H - 14}" text-anchor="middle">${LV[k]}</text>`).join("");
  const ends = [];
  D.models.forEach((m, i) => {
    const pts = xs.map((k, j) => [X(j), Y(m.levels[k][dose].pass)]);
    s += `<polyline fill="none" stroke="var(${COLORS[i]})" stroke-width="2" stroke-linejoin="round" points="${pts.map(p => p.join(",")).join(" ")}"/>`;
    s += pts.map((p, j) => { const c = m.levels[xs[j]][dose]; return `<circle cx="${p[0]}" cy="${p[1]}" r="5" fill="var(${COLORS[i]})" stroke="var(--card)" stroke-width="2" data-tip="${m.name}|${LV[xs[j]]}, ${dose} examples: ${c.k}/${c.n} whole job right"/>`; }).join("");
    ends.push([pts[2][1], m.name]);
  });
  ends.sort((a, b) => a[0] - b[0]);
  let last = -99;
  ends.forEach(([y, name]) => { const yy = Math.max(y, last + 15); last = yy; s += `<text class="lbl" x="${W - R + 12}" y="${yy + 4}">${name}</text>`; });
  svg.innerHTML = s;
  document.getElementById("legend").innerHTML = D.models.map((m, i) => `<span><i style="background:var(${COLORS[i]})"></i>${m.name}</span>`).join("");
  bindTips(svg);
}
function pill(v, tipx) { const c = v >= .67 ? "score-high" : v >= .34 ? "score-mid" : "score-low"; return `<span class="score-pill ${c} mono" ${tipx ? `data-tip="${tipx}"` : ""}>${P(v)}</span>`; }
function tables() {
  const H = D.models.map(m => `<th class="score">${m.name}</th>`).join("");
  const habitRow = (label, small, k) => `<tr><td>${label}<small>${small}</small></td>${D.models.map(m => `<td class="score">${m.habits[k] !== undefined ? pill(m.habits[k], `${m.name}|${label}: ${P1(m.habits[k])} of these invoices right`) : "-"}</td>`).join("")}</tr>`;
  document.getElementById("breaks").innerHTML = `<thead><tr><th>What the habit looks like (8-habit level, invoices right)</th>${H}</tr></thead><tbody>
    ${habitRow("Stable, routine", "small invoices, nothing special: no note, usual cost center", "routine")}
    ${habitRow("Stable, two conditions", "PO matched on unreviewed Infra; Selbourne coded by size; re-sent invoices marked duplicate", "two")}
    ${habitRow("Depends on the team", "who reviews depends on the supplier's team; Security kept the old cutoff", "team")}
    ${habitRow("Changed this autumn", "cutoff moved, contract supplier, reclassified cost center, card payments", "changed")}
    <tr><td>Contradicted by an old doc<small>8 habits + last year's policy, whole job right</small></td>${D.models.map(m => `<td class="score">${pill(m.levels.L3[5].pass, `${m.name}|${m.levels.L3[5].k}/${m.levels.L3[5].n} whole job right`)}</td>`).join("")}</tr>
    <tr><td>Told in plain words<small>control: all 8 habits stated in the instruction, whole job right</small></td>${D.models.map(m => `<td class="score">${pill(m.told.pass, `${m.name}|told: ${m.told.k}/${m.told.n} whole job right`)}</td>`).join("")}</tr>
  </tbody>`;
  const vers = [["L1", 3], ["L1", 5], ["L2", 3], ["L2", 5], ["L3", 3], ["L3", 5]];
  document.getElementById("versions").innerHTML = `<thead><tr><th>Version</th>${H}</tr></thead><tbody>${vers.map(([k, d]) =>
    `<tr><td>${LV[k]}<small>${d} examples per habit</small></td>${D.models.map(m => `<td class="score">${pill(m.levels[k][d].pass, `${m.name}|${m.levels[k][d].k}/${m.levels[k][d].n} whole job right, ${P1(m.levels[k][d].mean)} invoices right`)}</td>`).join("")}</tr>`).join("")}
    <tr><td>Told control<small>8 habits + old doc, all habits stated, 3 examples</small></td>${D.models.map(m => `<td class="score">${pill(m.told.pass)}</td>`).join("")}</tr>
    <tr><td>4 habits + dated old doc<small>side version, 2/3/5 examples pooled</small></td>${D.models.map(m => `<td class="score">${pill(m.l1_doc.pass)}</td>`).join("")}</tr></tbody>`;
  document.getElementById("base").innerHTML = `<thead><tr><th>Brainless script (no AI), 5 examples</th><th class="score">4 habits</th><th class="score">8 habits</th><th class="score">8 + old doc</th><th class="score">Invoices right</th></tr></thead><tbody>${D.baseline_summary.map(b =>
    `<tr><td>${b.name}</td><td class="score mono">${P(b.by.L1)}</td><td class="score mono">${P(b.by.L2)}</td><td class="score mono">${P(b.by.L3)}</td><td class="score mono">${P1(b.mean)}</td></tr>`).join("")}</tbody>`;
  document.getElementById("vendor").innerHTML = `<thead><tr><th>Model</th><th class="score">Shared plain agent</th><th class="score">Own agent</th></tr></thead><tbody>${D.vendor.map(v =>
    `<tr><td>${v.name}<small>own agent: ${v.agent}</small></td><td class="score mono">${P1(v.shared.pass)}</td><td class="score mono">${P1(v.own.pass)}</td></tr>`).join("")}</tbody>`;
  bindTips(document.getElementById("results"));
}
function insights() {
  const m = D.models, avg = a => a.reduce((s, x) => s + x, 0) / a.length;
  const l1 = avg(m.map(x => x.levels.L1[5].pass)), l2 = avg(m.map(x => x.levels.L2[5].pass)), l3 = avg(m.map(x => x.levels.L3[5].pass));
  const best2 = [...m].sort((a, b) => b.levels.L2[5].pass - a.levels.L2[5].pass)[0];
  const told = m.reduce((s, x) => s + x.told.k, 0), toldn = m.reduce((s, x) => s + x.told.n, 0);
  const rt = avg(m.map(x => x.habits.routine || 0)), ch = avg(m.map(x => x.habits.changed || 0)), tw = avg(m.map(x => x.habits.two || 0));
  const items = [
    ["More habits, fewer clean mornings.", `Average whole-job pass rate across models: ${P(l1)} with 4 habits, ${P(l2)} with 8, ${P(l3)} with 8 plus last year's policy doc. Same company, same evidence per habit.`],
    ["Routine is easy; changed and two-condition habits are not.", `On the 8-habit level, agents get ${P(rt)} of routine invoices right, ${P(tw)} of two-condition ones and ${P(ch)} of the habits that changed this autumn.`],
    ["Even the best agent rarely does the whole morning.", `With 8 habits, ${best2.name} gets all 15 invoices right in ${P(best2.levels.L2[5].pass)} of tries.`],
    ["It is the hidden habits, not the job.", `Told the 8 habits in the instruction, agents get ${told} of ${toldn} tries fully right.`],
  ];
  document.getElementById("insights").innerHTML = items.map(([b, s]) => `<li><b>${b}</b><span>${s}</span></li>`).join("");
}
function examples() {
  document.getElementById("trajectory-list").innerHTML = D.examples.map(e => `<article class="trajectory">
    <div><div class="eyebrow">${e.label}</div><h3>${e.model}</h3><code>${e.version}</code></div>
    <div>${e.quote ? `<blockquote>"${e.quote}"</blockquote>` : ""}<p><b>What we saw.</b> ${e.observed}</p><p><b>Why it matters.</b> ${e.why}</p><code>${e.run}</code></div></article>`).join("");
}
function fair() {
  const m = D.models, told = m.reduce((s, x) => s + x.told.k, 0), toldn = m.reduce((s, x) => s + x.told.n, 0);
  const dumb = D.baseline_summary.filter(b => !/same size/.test(b.name)), copy = D.baseline_summary.find(b => /same size/.test(b.name));
  const items = [
    ["Same agent for every model", "One plain loop, same instructions, one shell tool, same limits, effort high, no fallback model."],
    ["Told control", `With all 8 habits stated in the instruction: ${told}/${toldn} tries fully right. The box, tools and grader work; what is hard is finding the habits.`],
    ["Enough evidence", "Every habit is shown by at least 3 (or 5) recent examples in the tracker. Nothing hinges on a single row."],
    ["Grader tests", "Every version is graded against the obvious wrong answers before any model runs; the right answer scores 1, an empty tracker 0; notes are read by meaning, not exact wording."],
    ["Leak check", "Nothing in the sandbox holds the answer: no tests, no key, no solution; the habits only show as tracker rows."],
    ["Brainless baselines", `Scripts get ${P(Math.max(...dumb.map(b => b.pass)))} fully right. Copying the latest invoice of the same supplier and size gets ${copy ? P(copy.by.L1) : "n/a"} on 4 habits but ${copy ? P(copy.by.L2) : "n/a"} on 8: the 8-habit level needs more than lookup.`],
  ];
  document.getElementById("fairbox").innerHTML = items.map(([b, s]) => `<div><b>${b}</b><span>${s}</span></div>`).join("");
}
document.querySelectorAll("#score-toggle button").forEach(b => b.onclick = () => { mode = b.dataset.mode; document.querySelectorAll("#score-toggle button").forEach(x => x.setAttribute("aria-pressed", x === b)); rows(); });
document.querySelectorAll("#doc-toggle button").forEach(b => b.onclick = () => { lev = b.dataset.doc; document.querySelectorAll("#doc-toggle button").forEach(x => x.setAttribute("aria-pressed", x === b)); rows(); });
document.querySelectorAll("#curve-toggle button").forEach(b => b.onclick = () => { dose = +b.dataset.c; document.querySelectorAll("#curve-toggle button").forEach(x => x.setAttribute("aria-pressed", x === b)); curve(); });
document.querySelectorAll(".tabs button").forEach(b => b.onclick = () => { document.querySelectorAll(".tabs button").forEach(x => x.setAttribute("aria-selected", x === b));
  ["t-breaks","t-versions","t-base","t-vendor"].forEach(id => document.getElementById(id).hidden = id !== b.dataset.tab); });
rows(); curve(); tables(); insights(); examples(); fair();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    data = build_data()
    (HERE / "leaderboard.html").write_text(page(data))
    for m in data["models"]:
        lv = m["levels"]
        print(f"{m['name']:18s} main {m['main']['k']}/{m['main']['n']}  L1 {lv['L1'][5]['k']}/{lv['L1'][5]['n']}  "
              f"L2 {lv['L2'][5]['k']}/{lv['L2'][5]['n']}  L3 {lv['L3'][5]['k']}/{lv['L3'][5]['n']}  told {m['told']['k']}/{m['told']['n']}")
