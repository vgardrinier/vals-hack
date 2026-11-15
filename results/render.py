"""Render results/v3_attempts.json into results/leaderboard.html (Mercor APEX-style layout).

    python3 results/render.py

Two metrics, picked in the card's dropdown:
  Rule score  mean over attempts of the share of the hidden rule's 3 parts the agent showed:
                1. asked the director about the one invoice that needs approval
                2. knew the cutoff moved to $10k (asked (1) and left the $7,280 and $6,925 ones alone)
                3. knew Halverson is exempt (asked (1) and left Halverson's $11,340.50 alone)
              Parts 2 and 3 only count once part 1 holds: an agent that asks nobody gets no
              credit for "not bothering" the director.
              Interval: 95% bootstrap over attempts, 10,000 resamples.
  Pass rate   share of attempts passing every check. Interval: 95% Wilson.
Three levels, picked in the second dropdown: rule only in past work / also written in an
email / told in the instruction.
"""

import json
import math
import random
from html import escape
from pathlib import Path

HERE = Path(__file__).parent
# the old no-pointer level is gone from the page: the ladder is all no-pointer, and its task 5 is that same task
LEVELS = [("nudged", "Pointed at past work, rule unstated"),
          ("written", "Rule in an email somewhere"), ("told", "Rule told in the instruction")]
MODELS = {
    "claude-fable-5-2": ("Fable 5.2", "Anthropic"),
    "claude-opus-5-5": ("Opus 5.5", "Anthropic"),
    "claude-sonnet-5-5": ("Sonnet 5.5", "Anthropic"),
    "claude-haiku-5-5": ("Haiku 5.5", "Anthropic"),
    "gpt-6-astra": ("GPT-6 Astra", "OpenAI"),
    "gpt-6.1-sol": ("GPT-6.1 Sol", "OpenAI"),
}
AGENT = {"Anthropic": "Claude Code", "OpenAI": "Codex"}
FABLE_QUOTE = ("The three existing Q4 Wrenfield rows are under G&A, while the policy and the Q2/Q3 trackers "
               "say Marketing. I left those rows alone, so the tracker is now inconsistent until someone confirms which is right.")


def rule_parts(a: dict) -> list[bool]:
    checks = a["checks"]

    def ok(vendor: str, phrase: str) -> bool:
        return any(c.startswith("PASS") and f"({vendor}," in c and phrase in c for c in checks)

    asked = ok("Ironwood", "sent to director for approval")
    threshold = asked and ok("Calloway", "NOT sent") and ok("Marrow", "NOT sent")
    exception = asked and ok("Halverson", "NOT sent")
    return [asked, threshold, exception]


def failure_kind(a: dict) -> str:
    asked, threshold, exception = rule_parts(a)
    if not asked:
        return "never asked for approval"
    if not threshold and not exception:
        return "used the old $5k rule"
    if not exception:
        return "missed the Halverson exception"
    if not threshold:
        return "missed the $10k change"
    return "bookkeeping mistakes"


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = k / n
    den = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, mid - half), min(1.0, mid + half)


def bootstrap(xs: list[float], reps: int = 10000, seed: int = 0) -> tuple[float, float]:
    if not xs:
        return 0.0, 0.0
    rng = random.Random(seed)
    means = sorted(sum(rng.choice(xs) for _ in xs) / len(xs) for _ in range(reps))
    return means[int(.025 * reps)], means[int(.975 * reps) - 1]


def summarize(attempts: list[dict]) -> dict:
    out = {}
    for model, (name, lab) in MODELS.items():
        per = {}
        for lvl, _ in LEVELS:
            sc = [a for a in attempts if a["model"] == model and a["version"] == lvl
                  and a["status"] == "FINISHED" and a["reward"] is not None]
            if not sc:
                continue
            k, n = sum(int(a["reward"]) for a in sc), len(sc)
            parts = [sum(rule_parts(a)) / 3 for a in sc]
            kinds = [failure_kind(a) for a in sc if a["reward"] != 1]
            per[lvl] = {
                "n": n, "k": k,
                "pass": [k / n, *wilson(k, n)],
                "rule": [sum(parts) / n, *bootstrap(parts)],
                "fails": {kd: kinds.count(kd) for kd in dict.fromkeys(kinds)},
            }
        if per:
            out[model] = {"name": name, "lab": lab, "agent": AGENT[lab], "levels": per}
    return out


LADDER = [("ladder-1-tracker-review", "REVIEW note", "tracker"),
          ("ladder-2-tracker-change", "Cutoff moved", "tracker"),
          ("ladder-3-tracker-exception", "Supplier exception", "tracker"),
          ("ladder-4-email-approval", "Approval by email", "email"),
          ("invoice-approval-v3", "Cutoff moved + exception", "email"),
          ("ladder-6-email-deputy", "Director on leave", "email")]


def summarize_ladder(data: dict, attempts: list[dict]) -> int:
    """Add a 'ladder' level per model. Returns tries per task (max)."""
    done = [a for a in attempts if a["status"] == "FINISHED" and a["score"] is not None]
    tries = 0
    for model, (name, lab) in MODELS.items():
        mine = [a for a in done if a["model"] == model]
        if not mine:
            continue
        runs = sorted({a["run_id"] for a in mine})
        per_run = [sum(a["score"] for a in mine if a["run_id"] == r) /
                   len([a for a in mine if a["run_id"] == r]) for r in runs]
        k, n = sum(int(a["reward"]) for a in mine), len(mine)
        tasks = {}
        for t, _, _ in LADDER:
            xs = [a for a in mine if a["task"] == t]
            if xs:
                tasks[t] = {"score": sum(a["score"] for a in xs) / len(xs),
                            "k": sum(int(a["reward"]) for a in xs), "n": len(xs)}
                tries = max(tries, len(xs))
        weak = min(tasks.items(), key=lambda kv: kv[1]["score"]) if tasks else None
        entry = data.setdefault(model, {"name": name, "lab": lab, "agent": AGENT[lab], "levels": {}})
        entry["levels"]["ladder"] = {
            "n": n, "k": k, "runs": len(runs), "tasks": tasks,
            "pass": [k / n, *wilson(k, n)],
            "rule": [sum(per_run) / len(per_run), *bootstrap(per_run)],
            "fails": ({f"weakest: {dict((t, l) for t, l, _ in LADDER)[weak[0]]}": f"{weak[1]['score'] * 100:.0f}%"}
                      if weak and weak[1]["score"] < 1 else {}),
        }
    return tries


DRIFT_TYPES = [("cutoff", "Cutoff moved", "REVIEW cutoff went from $5k to $10k"),
               ("stopped", "Habit stopped", "the team stopped marking REVIEW"),
               ("approver", "Approver changed", "approvals moved from Mireille (MA) to Rosalind (RQ)"),
               ("returned", "Habit came back", "REVIEW paused for six weeks, then came back")]
DRIFT_DOSES = [1, 3, 7]
SHARED = "High"


def summarize_drift(data: dict, attempts: list[dict], key: str = "drift_old") -> int:
    """Add the single-habit drift level per model (shared agent). Returns tries per version."""
    done = [a for a in attempts if a["status"] == "FINISHED" and a["reward"] is not None]
    tries = 0
    for model, (name, lab) in MODELS.items():
        mine = [a for a in done if a["model"] == model]
        if not mine:
            continue
        scores = [a["score"] for a in mine]
        k, n = sum(int(a["reward"]) for a in mine), len(mine)
        cells, dose, kind = {}, {}, {}
        for t, _, _ in DRIFT_TYPES:
            for d in DRIFT_DOSES:
                xs = [a for a in mine if a["type"] == t and a["dose"] == d]
                if xs:
                    cells[f"{t}-{d}"] = {"score": sum(a["score"] for a in xs) / len(xs),
                                         "k": sum(int(a["reward"]) for a in xs), "n": len(xs)}
                    tries = max(tries, len(xs))
        for d in DRIFT_DOSES:
            xs = [a["score"] for a in mine if a["dose"] == d]
            if xs:
                dose[str(d)] = [sum(xs) / len(xs), *bootstrap(xs)]
        for t, _, _ in DRIFT_TYPES:
            xs = [a["score"] for a in mine if a["type"] == t]
            if xs:
                kind[t] = sum(xs) / len(xs)
        fails, by_type = {}, {}
        for a in mine:
            if a["reward"] != 1:
                kd = a.get("kind_of_miss", "other")
                fails[kd] = fails.get(kd, 0) + 1
                by_type.setdefault(a["type"], {})[kd] = by_type.setdefault(a["type"], {}).get(kd, 0) + 1
        entry = data.setdefault(model, {"name": name, "lab": lab, "agent": AGENT[lab], "levels": {}})
        entry["levels"][key] = {
            "n": n, "k": k, "agent": SHARED, "cells": cells, "dose": dose, "kind": kind,
            "pass": [k / n, *wilson(k, n)], "rule": [sum(scores) / n, *bootstrap(scores)], "fails": fails,
            "fails_by_type": by_type,
        }
    return tries


MORNING_HABITS = [("cutoff", "Cutoff", "$5k to $10k, Security kept $5k"),
                  ("reviewer", "Reviewer", "Tomasz for Infra, Mireille otherwise"),
                  ("contract", "Contract supplier", "Halverson stopped getting REVIEW"),
                  ("costcenter", "Cost center", "Wrenfield moved to G&A")]
MORNING_DOSES = [1, 2, 3]


def morning_miss(a: dict) -> str:
    """How a failed morning try went wrong, read from the grader lines."""
    import re as _re
    fails = [l for l in a["checks"] if l.startswith("FAIL")]
    if any("logged" in l or "past rows" in l for l in fails):
        return "bookkeeping"
    def old(l):
        m = _re.search(r"\(([^,]+), \$([\d,\.]+)\)", l)
        vendor, amt = m.group(1), float(m.group(2).replace(",", ""))
        ok = True
        if "note " in l:
            ok &= ("note 'REVIEW' " in l) if amt > 5000 else ("note 'none'" in l)
        if "cost center" in l:
            ok &= vendor == "Wrenfield" and "'Marketing'" in l
        return ok
    if all(old(l) for l in fails):
        return "followed the handbook" if a.get("handbook") else "kept the old habits"
    if all("note 'REVIEW' want 'REVIEW:" in l for l in fails):
        return "missed the reviewer names"
    return "caught some changes, not all"


def summarize_morning(data: dict, attempts: list[dict]) -> int:
    """Main benchmark: the messy monday morning. Dose curve and habit grid use the versions without
    the handbook (all three doses exist there); the handbook tab compares 2 and 3 examples with vs without."""
    done = [a for a in attempts if a["status"] == "FINISHED" and a["reward"] is not None]
    tries = 0
    for model, (name, lab) in MODELS.items():
        mine = [a for a in done if a["model"] == model]
        if not mine:
            continue
        scores = [a["reward"] for a in mine]
        k, n = sum(1 for x in scores if x == 1), len(mine)
        plain = [a for a in mine if not a["handbook"]]
        cells, dose, kind = {}, {}, {}
        for h, _, _ in MORNING_HABITS:
            for d in MORNING_DOSES:
                xs = [a["habits"][h] for a in plain if a["dose"] == d and h in a["habits"]]
                if xs:
                    cells[f"{h}-{d}"] = {"score": sum(xs) / len(xs), "n": len(xs),
                                         "k": sum(1 for x in xs if x == 1)}
            xs = [a["habits"][h] for a in plain if h in a["habits"]]
            if xs:
                kind[h] = sum(xs) / len(xs)
        for d in MORNING_DOSES:
            xs = [a["reward"] for a in plain if a["dose"] == d]
            if xs:
                dose[str(d)] = [sum(xs) / len(xs), *bootstrap(xs)]
                tries = max(tries, len(xs))
        pair = lambda hb: [a["reward"] for a in mine if a["handbook"] == hb and a["dose"] in (2, 3)]
        hb = {}
        for key_, flag in (("no", False), ("yes", True)):
            xs = pair(flag)
            if xs:
                hb[key_] = [sum(xs) / len(xs), *bootstrap(xs)]
        fails, by_hb = {}, {}
        for a in mine:
            if a["reward"] != 1:
                kd = morning_miss(a)
                fails[kd] = fails.get(kd, 0) + 1
        hb["followed"] = fails.get("followed the handbook", 0)
        hb["n"] = sum(1 for a in mine if a["handbook"])
        entry = data.setdefault(model, {"name": name, "lab": lab, "agent": AGENT[lab], "levels": {}})
        entry["levels"]["drift"] = {
            "n": n, "k": k, "agent": SHARED, "cells": cells, "dose": dose, "kind": kind, "hb": hb,
            "pass": [k / n, *wilson(k, n)], "rule": [sum(scores) / n, *bootstrap(scores)], "fails": fails,
            "fails_by_type": {},
        }
    return tries


def page(data: dict) -> str:
    lad = [m for m in data.values() if "ladder" in m["levels"]]
    dri = [m for m in data.values() if "drift" in m["levels"]]
    old = [m for m in data.values() if "drift_old" in m["levels"]]
    levels = ([("drift", "Main benchmark")] if dri else []) + \
             ([("drift_old", "Earlier: one habit changes")] if old else []) + \
             ([("ladder", "Earlier: 6-task ladder")] if lad else []) + \
             [(k, f"Earlier: {l[0].lower() + l[1:]}") for k, l in LEVELS]
    if dri:
        top = max((m["levels"]["drift"]["rule"][0], m["name"]) for m in dri)
        tries = max(c["n"] for m in dri for c in m["levels"]["drift"]["cells"].values())
        stats = [(str(len(dri)), "Frontier models"), (str(len(MORNING_HABITS)), "Habits changing at once"),
                 ("15", "Invoices per try"), (f"{top[0] * 100:.1f}%", "Top score")]
    elif lad:
        top = max((m["levels"]["ladder"]["rule"][0], m["name"]) for m in lad)
        stats = [(str(len(lad)), "Frontier models"), (str(len(LADDER)), "Tasks, easy to hard"),
                 (str(max(t["n"] for m in lad for t in m["levels"]["ladder"]["tasks"].values())), "Tries per task"),
                 (f"{top[0] * 100:.1f}%", "Top ladder score")]
    else:
        top = max((m["levels"]["nudged"]["rule"][0], m["name"]) for m in data.values() if "nudged" in m["levels"])
        stats = [(str(len(data)), "Frontier models"), ("3", "Levels of hidden"), ("3–8", "Attempts per level"),
                 (f"{top[0] * 100:.1f}%", "Top rule score, pointed")]
    stats_html = "".join(f'<div class="stat"><div class="v">{v}</div><div class="k">{k}</div></div>' for v, k in stats)
    blob = json.dumps({"models": data, "levels": levels, "quote": FABLE_QUOTE,
                       "ladder": [[t, l, w] for t, l, w in LADDER],
                       "drift": {"types": MORNING_HABITS, "doses": MORNING_DOSES},
                       "order": list(MODELS)})
    icons = {lab: (HERE / "icons" / f).read_text().replace("<title>", "<title>").strip()
             for lab, f in [("Anthropic", "anthropic.svg"), ("OpenAI", "openai.svg")]}
    icons = {k: v.replace('role="img"', 'role="img" aria-hidden="true"') for k, v in icons.items()}
    return (TEMPLATE.replace("__DATA__", blob).replace("__STATS__", stats_html)
            .replace("__ICONS__", json.dumps(icons)).replace("__ANTHROPIC__", icons["Anthropic"]))


TEMPLATE = r"""<!doctype html>
<html lang="en" class="viz-root">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PrecedentBench: can AI agents follow the rules nobody wrote down?</title>
<style>
.viz-root {
  color-scheme: light;
  --surface-1: #ffffff; --surface-2: #f5f5f4; --card: #ffffff; --line: #e7e7e4; --track: #f1f1f0;
  --text-primary: #0b0b0b; --text-secondary: #4b4b48; --text-muted: #8b8b87;
  --accent: #4f46e5;
  --anthropic-a: #f6a879; --anthropic-b: #e8672f; --anthropic-c: #b9471a;
  --openai-a: #7fd6b5; --openai-b: #16a06e; --openai-c: #0c7650;
  --whisker: #a3a39e; --cell-0: #f1f1f0; --cell-ink: #0b0b0b; --quote-bg: #0f0f0e; --quote-ink: #f5f5f4;
  --s1: #2a78d6; --s2: #eb6834; --s3: #1baf7a; --s4: #eda100; --s5: #e87ba4; --grid: #e7e7e4;
}
@media (prefers-color-scheme: dark) {
  :root:where(:not([data-theme="light"])).viz-root {
    color-scheme: dark;
    --surface-1: #121211; --surface-2: #1c1c1a; --card: #171716; --line: #2c2c29; --track: #262624;
    --text-primary: #f0efec; --text-secondary: #c3c2b9; --text-muted: #8d8c85; --accent: #7c74f0;
    --anthropic-a: #a8501f; --anthropic-b: #e0632b; --anthropic-c: #f39a6a;
    --openai-a: #0f6b4a; --openai-b: #1aa874; --openai-c: #5fd3a5;
    --whisker: #6f6e68; --cell-0: #262624; --cell-ink: #f0efec; --quote-bg: #f0efec; --quote-ink: #121211;
    --s1: #3987e5; --s2: #d95926; --s3: #199e70; --s4: #c98500; --s5: #d55181; --grid: #2c2c29;
  }
}
:root[data-theme="dark"].viz-root {
  color-scheme: dark;
  --surface-1: #121211; --surface-2: #1c1c1a; --card: #171716; --line: #2c2c29; --track: #262624;
  --text-primary: #f0efec; --text-secondary: #c3c2b9; --text-muted: #8d8c85; --accent: #7c74f0;
  --anthropic-a: #a8501f; --anthropic-b: #e0632b; --anthropic-c: #f39a6a;
  --openai-a: #0f6b4a; --openai-b: #1aa874; --openai-c: #5fd3a5;
  --whisker: #6f6e68; --cell-0: #262624; --cell-ink: #f0efec; --quote-bg: #f0efec; --quote-ink: #121211;
  --s1: #3987e5; --s2: #d95926; --s3: #199e70; --s4: #c98500; --s5: #d55181; --grid: #2c2c29;
}
.dose-wrap { display: grid; grid-template-columns: 1fr 220px; gap: 28px; align-items: start; }
.dose svg { width: 100%; height: auto; display: block; overflow: visible; }
.dose .gl { stroke: var(--grid); stroke-width: 1; }
.dose .ax { fill: var(--text-muted); font-size: 11px; }
.dose .ln { fill: none; stroke-width: 2; stroke-linejoin: round; stroke-linecap: round; }
.dose .pt { stroke: var(--card); stroke-width: 2; cursor: default; }
.dose .hit { fill: transparent; }
.dose .lab { font-size: 12px; fill: var(--text-secondary); }
.legend2 { list-style: none; margin: 0; padding: 0; font-size: 13px; color: var(--text-secondary); }
.legend2 li { display: flex; align-items: center; gap: 8px; padding: 5px 0; }
.legend2 i { width: 18px; height: 2px; border-radius: 1px; display: inline-block; position: relative; }
.legend2 i::after { content: ""; position: absolute; left: 5px; top: -3px; width: 8px; height: 8px; border-radius: 50%; background: inherit; }
.legend2 .v { margin-left: auto; color: var(--text-primary); font-variant-numeric: tabular-nums; }
.note { color: var(--text-muted); font-size: 13px; margin: 6px 0 18px; }
@media (max-width: 900px) { .dose-wrap { grid-template-columns: 1fr; } }
* { box-sizing: border-box; }
body { margin: 0; background: var(--surface-1); color: var(--text-primary);
  font: 15px/1.55 Inter, ui-sans-serif, -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
  -webkit-font-smoothing: antialiased; }
a { color: inherit; }
.mono { font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; font-variant-numeric: tabular-nums; }
.wrap { max-width: 1180px; margin: 0 auto; padding: 0 48px; }
nav.top { border-bottom: 1px solid var(--line); }
nav.top .wrap { display: flex; align-items: center; height: 64px; gap: 36px; }
.brand { display: flex; align-items: center; gap: 9px; font-weight: 650; font-size: 16px; letter-spacing: -.01em; text-decoration: none; }
.brand i { width: 22px; height: 22px; border-radius: 6px; background: linear-gradient(135deg, #8b85f5, var(--accent)); display: inline-block; }
.navlinks { display: flex; gap: 30px; font-size: 14px; }
.navlinks a { text-decoration: none; color: var(--text-primary); }
.navlinks a:hover { color: var(--accent); }
.navright { margin-left: auto; font-size: 13px; border: 1px solid var(--line); border-radius: 6px; padding: 7px 16px; text-decoration: none; }
.crumbs { font-size: 12px; color: var(--text-muted); padding: 14px 0; }
.crumbs b { color: var(--text-primary); font-weight: 500; }
.crumbs span { margin: 0 7px; }
.hero { text-align: center; padding: 64px 0 60px; }
.hero h1 { font-size: 48px; line-height: 1.1; font-weight: 450; letter-spacing: -.025em; margin: 0 0 18px; }
.hero .with { color: var(--text-muted); font-size: 13px; margin-bottom: 22px; display: flex; gap: 8px; justify-content: center; align-items: baseline; }
.hero .with b { color: var(--text-primary); font-size: 17px; font-weight: 650; letter-spacing: -.02em; }
.hero p { color: var(--text-secondary); max-width: 600px; margin: 0 auto 26px; }
.btns { display: flex; gap: 10px; justify-content: center; }
.btn { font: inherit; font-size: 13px; padding: 9px 18px; border-radius: 6px; text-decoration: none;
  background: var(--surface-2); color: var(--text-primary); border: 1px solid var(--line); }
.btn.primary { background: var(--accent); color: #fff; border-color: var(--accent); }
.stats { display: grid; grid-template-columns: repeat(4, 1fr); padding: 40px 0 96px; }
.stat { text-align: center; border-left: 1px solid var(--line); padding: 6px 0; }
.stat:first-child { border-left: 0; }
.stat .v { font-size: 44px; font-weight: 400; letter-spacing: -.02em; line-height: 1.15; }
.stat .k { color: var(--text-muted); font-size: 17px; }
.lb { display: grid; grid-template-columns: 1fr 1fr; gap: 64px; align-items: start; padding-bottom: 110px; }
h2 { font-size: 21px; font-weight: 500; margin: 0 0 22px; letter-spacing: -.01em; }
.lb .copy p { color: var(--text-secondary); margin: 0 0 18px; }
.chips { display: flex; gap: 8px; margin-top: 26px; flex-wrap: wrap; }
.chips a { font-size: 13px; background: var(--surface-2); border-radius: 6px; padding: 6px 12px; text-decoration: none; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 26px 28px 30px; }
.card-head { display: flex; justify-content: space-between; color: var(--text-muted); font-size: 13px; margin-bottom: 8px; }
.lrow { padding: 13px 0 12px; outline: none; border-radius: 6px; cursor: default; }
.lrow:hover .mname, .lrow:focus-visible .mname { color: var(--accent); }
.ltop { display: flex; justify-content: space-between; align-items: center; gap: 10px; }
.mname { font-size: 16px; font-weight: 500; display: flex; align-items: center; gap: 7px; }
.mname svg { width: 16px; height: 16px; fill: currentColor; flex: none; }
.mtag { color: var(--text-muted); font-size: 12.5px; font-weight: 400; }
.mscore { font-size: 14px; white-space: nowrap; }
.mscore .pm { color: var(--text-muted); font-size: 12.5px; margin-left: 7px; }
.lbar { position: relative; height: 6px; margin-top: 10px; background: var(--track); border-radius: 3px; }
.lbar .fill { position: absolute; left: 0; top: 0; bottom: 0; border-radius: 3px; }
.lbar .lo { position: absolute; top: 0; bottom: 0; border-radius: 0 3px 3px 0; }
.lbar .lo::before { content: ""; position: absolute; left: 0; top: -1px; bottom: -1px; width: 1px; background: var(--whisker); opacity: .7; }
.lbar .wh { position: absolute; top: 50%; height: 1px; background: var(--whisker); }
.lbar .wh::after { content: ""; position: absolute; right: -1px; top: -3px; width: 1px; height: 7px; background: var(--whisker); }
.axis { position: relative; height: 24px; margin-top: 30px; border-top: 1px solid var(--line); }
.axis span { position: absolute; top: 9px; transform: translateX(-50%); color: var(--text-muted); font-size: 12px; opacity: .8; }
.axis span:first-child { transform: none; }
.axis span:last-child { transform: translateX(-100%); }
.card-foot { display: flex; justify-content: space-between; align-items: center; margin-top: 34px; gap: 10px; }
.card-foot > a { white-space: nowrap; }
.card-foot > a { font-size: 14px; text-decoration: none; }
.card-foot > a:hover { color: var(--accent); }
.selects { display: flex; gap: 14px; align-items: center; }
.sel { position: relative; font-size: 14px; }
.sel select { max-width: 190px; text-overflow: ellipsis; appearance: none; -webkit-appearance: none; font: inherit; color: var(--text-primary); background: transparent;
  border: 0; padding: 2px 22px 2px 0; cursor: pointer; text-align: right; }
.sel::after { content: ""; position: absolute; right: 4px; top: 7px; width: 6px; height: 6px; border-right: 1.3px solid var(--text-muted);
  border-bottom: 1.3px solid var(--text-muted); transform: rotate(45deg); pointer-events: none; }
.sel select:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 4px; }
.kt { display: grid; grid-template-columns: 1.15fr .85fr; gap: 56px; align-items: start; padding-bottom: 110px; }
.takeaways { list-style: none; padding: 0; margin: 0; counter-reset: t; }
.takeaways li { counter-increment: t; padding: 18px 0 18px 30px; border-bottom: 1px solid var(--line); position: relative; }
.takeaways li::before { content: counter(t); position: absolute; left: 8px; top: 18px; color: var(--accent); font-size: 15px; }
.takeaways b { display: block; font-weight: 500; font-size: 16px; margin-bottom: 4px; }
.takeaways span { color: var(--text-secondary); font-size: 13.5px; }
.quote { background: var(--quote-bg); color: var(--quote-ink); border-radius: 10px; padding: 34px 32px; margin-top: 40px; }
.quote q { display: block; font-size: 21px; line-height: 1.4; letter-spacing: -.01em; quotes: "\201C" "\201D"; }
.quote .who { margin-top: 22px; font-size: 13px; opacity: .7; display: flex; gap: 8px; align-items: center; }
.quote .who svg { width: 14px; height: 14px; fill: currentColor; }
.sec { padding: 0 0 100px; }
.sub { color: var(--text-secondary); margin: -10px 0 26px; max-width: 640px; }
.tabs { display: flex; gap: 26px; border-bottom: 1px solid var(--line); margin-bottom: 30px; }
.tabs button { font: inherit; font-size: 14px; background: none; border: 0; padding: 0 0 10px; color: var(--text-secondary);
  cursor: pointer; border-bottom: 2px solid transparent; margin-bottom: -1px; }
.tabs button[aria-selected="true"] { color: var(--accent); border-bottom-color: var(--accent); }
.grid { width: 100%; border-collapse: separate; border-spacing: 2px; }
.grid th { color: var(--text-muted); font-weight: 400; font-size: 12.5px; text-align: left; padding: 8px 10px; vertical-align: bottom; }
.grid th.c { text-align: center; }
.grid th small { display: block; opacity: .8; }
.grid td { padding: 0; }
.grid td.nm { padding: 0 16px 0 4px; white-space: nowrap; font-weight: 500; }
.grid td.nm svg { width: 14px; height: 14px; fill: currentColor; vertical-align: -2px; margin-right: 6px; }
.cell { height: 48px; border-radius: 4px; display: flex; flex-direction: column; align-items: center; justify-content: center; font-size: 14px; }
.cell small { font-size: 11px; opacity: .8; }
table.plain { width: 100%; border-collapse: collapse; font-size: 14px; }
table.plain th, table.plain td { text-align: left; padding: 10px 8px; border-bottom: 1px solid var(--line); }
table.plain th { color: var(--text-muted); font-weight: 400; font-size: 12.5px; }
.method { color: var(--text-secondary); font-size: 14px; max-width: 820px; }
.method p { margin: 0 0 12px; }
.method b { color: var(--text-primary); font-weight: 500; }
footer { border-top: 1px solid var(--line); color: var(--text-muted); font-size: 12px; padding: 22px 0 40px; }
.tip { position: fixed; pointer-events: none; background: var(--text-primary); color: var(--surface-1);
  font-size: 12.5px; padding: 9px 11px; border-radius: 8px; max-width: 320px; line-height: 1.45; z-index: 9; }
.tip b { display: block; margin-bottom: 3px; }
[hidden] { display: none !important; }
@media (max-width: 920px) {
  .lb, .kt { grid-template-columns: 1fr; }
  .stats { grid-template-columns: repeat(2, 1fr); row-gap: 24px; }
  .hero h1 { font-size: 34px; }
  .navlinks { display: none; }
  .wrap { padding: 0 22px; }
}
</style>
</head>
<body>
<nav class="top"><div class="wrap">
  <a class="brand" href="#"><i></i>PrecedentBench</a>
  <div class="navlinks"><a href="#leaderboard">Leaderboard</a><a href="#results">Results</a><a href="#method">Methodology</a><a href="#takeaways">Takeaways</a></div>
  <a class="navright" href="#method">Vals Hacks 2026</a>
</div></nav>
<div class="wrap">
  <div class="crumbs">Home<span>›</span>Benchmarks<span>›</span><b>PrecedentBench</b></div>

  <section class="hero">
    <h1>Can AI agents follow the rules<br>nobody wrote down?</h1>
    <div class="with">Built on <b>Valkyrie</b> · run on <b>Modal</b></div>
    <p>PrecedentBench drops an agent into a company's finance team and checks whether it does the job the way this
    team does it, using only what the team did before. Nobody wrote the changes down.</p>
    <div class="btns"><a class="btn primary" href="#leaderboard">See the leaderboard</a><a class="btn" href="#method">Read methodology</a></div>
  </section>

  <section class="stats">__STATS__</section>

  <section class="lb" id="leaderboard">
    <div class="copy">
      <h2>The PrecedentBench leaderboard</h2>
      <p>It's Monday at Redwood Inference. Fifteen supplier invoices are in the finance inbox, and the request is one
      line: log them in this quarter's tracker. Around them sit two archived quarters of trackers, about 300 invoices,
      and 2,500 company emails, Slack threads and tickets.</p>
      <p>This quarter the team quietly changed four habits at once. The review cutoff went from $5,000 to $10,000,
      except for Security. Review notes started naming who reviews. One supplier stopped needing review after signing
      a contract. Another moved to a different cost center. Nobody wrote any of it down; the only clue is how the last
      few weeks of rows look. In some versions an old AP policy in the shared drive still states the old rules.</p>
      <p>Each version shows 1, 2 or 3 invoices handled the new way per habit. A careful new hire would catch on. The
      score is the share of the 15 invoices the agent logs the team's current way.</p>
      <p>Every model runs in the same plain agent: same instructions, one terminal tool, same limits.</p>
      <div class="chips"><a href="#results">Dose curve</a><a href="#takeaways">Takeaways</a><a href="#method">Methodology</a></div>
    </div>
    <div class="card">
      <div class="card-head"><span>Model</span><span>Score</span></div>
      <div id="rows"></div>
      <div class="axis" id="axis"></div>
      <div class="card-foot">
        <a href="#results">View results for all tasks</a>
        <div class="selects">
          <div class="sel"><select id="level" aria-label="Level"></select></div>
          <div class="sel"><select id="metric" aria-label="Metric">
            <option value="rule">Mean Score</option>
            <option value="pass">Pass@1</option>
          </select></div>
        </div>
      </div>
    </div>
  </section>

  <section class="kt" id="takeaways">
    <div>
      <h2>Key takeaways</h2>
      <ol class="takeaways" id="tk"></ol>
    </div>
    <div class="quote">
      <q id="quote"></q>
      <div class="who">__ANTHROPIC__ Fable 5.2, after following the old AP policy in the shared drive (counted as a miss)</div>
    </div>
  </section>

  <section class="sec" id="results">
    <h2>Results</h2>
    <p class="sub">How much evidence each model needs before it notices the team changed its habits, and what an out of date handbook does to it.</p>
    <div class="tabs" role="tablist">
      <button role="tab" aria-selected="true" data-tab="t-dose">Dose curve</button>
      <button role="tab" aria-selected="false" data-tab="t-kind">By habit</button>
      <button role="tab" aria-selected="false" data-tab="t-hb">With vs without the handbook</button>
      <button role="tab" aria-selected="false" data-tab="t-table">Table</button>
      <button role="tab" aria-selected="false" data-tab="t-ladder">Earlier: ladder</button>
      <button role="tab" aria-selected="false" data-tab="t-levels">Earlier: levels</button>
    </div>
    <div id="t-dose"><div class="dose-wrap"><div class="dose" id="dose"></div><ul class="legend2" id="dleg"></ul></div>
      <p class="note">Score = share of the 15 invoices logged the team's current way, versions without the handbook, five
      tries each. Hover a point for details.</p></div>
    <div id="t-kind" hidden><table class="grid" id="kgrid"></table>
      <p class="note">Each cell: share of that habit's invoices handled the team's current way, versions without the
      handbook, small numbers per number of examples.</p>
      <p class="note" id="hes-note"></p></div>
    <div id="t-hb" hidden><table class="grid" id="hbgrid"></table>
      <p class="note">The stale handbook is an AP policy dated January 2026 in the shared drive. It states the old rules
      (REVIEW over $5,000, Wrenfield coded to Marketing) and says nothing about the changes. "Followed the handbook" counts
      tries whose every mistake matches the written policy. The version with 1 example and the handbook is not scored:
      one deviating row per habit against a written policy and 40 old rows is a defensible reading either way.</p></div>
    <div id="t-ladder" hidden><p class="note">Earlier experiment. Each model ran in its own vendor's agent (Claude Code or
      Codex), not the shared agent, so these numbers mix the model and the product around it.</p>
      <table class="grid" id="lgrid"></table></div>
    <div id="t-levels" hidden><p class="note">Earlier experiment, vendor agents (Claude Code or Codex), not the shared agent.</p>
      <p class="sub" style="margin-top:0">The approval task (task 5) run four ways. Same company, same invoices, same checks;
      only where the rule lives changes.</p>
      <table class="grid" id="grid"></table>
    </div>
    <div id="t-table" hidden><table class="plain" id="ptable"></table></div>
  </section>

  <section class="sec method" id="method">
    <h2>Methodology</h2>
    <p><b>Main benchmark: a messy monday.</b> The agent logs 15 supplier invoices in the live quarterly tracker. History:
    two archived quarterly trackers and the live one, about 300 invoices, plus 2,500 Redwood Inference emails, Slack threads
    and tickets (including hundreds about invoices, billing and vendors, filtered so none contradicts the habits). Four
    habits changed in Q4, none written down: (1) the REVIEW cutoff moved from $5,000 to $10,000 on Oct 5, except Security
    invoices, which kept $5,000; (2) since Oct 5 the note names the reviewer, "REVIEW: Tomasz" for Infra and "REVIEW:
    Mireille" otherwise; (3) Halverson Data Centers signed a contract on Nov 2 (the countersigned-contract email is in the
    history, it says nothing about review) and its invoices get no REVIEW since; (4) Wrenfield Creative moved from
    Marketing to G&A on Oct 12. Human mess: two big invoices before October where someone forgot REVIEW, and a few vendor
    name typos. Versions: 1, 2 or 3 rows showing each new habit, and with or without a stale AP policy stating the old
    rules (the 1-example version with the policy is not scored, see the handbook tab). Every one of the 15 invoices touches
    a changed habit. <b>Score</b> per try: the share of the 15 invoices logged exactly once with the right note (no REVIEW,
    or REVIEW naming the right reviewer) and the right cost center; zero if any past row was changed. Mean Score is the
    mean over tries; Pass@1 the share of tries with all 15 right. The design and the rules for adjusting it overnight were
    written before any results: docs/plans/next-iteration-messy-morning.md. Round 1 was a pilot; round 2 dropped the
    ambiguous version, fixed round-number invoice amounts, and made the cutoff change partial (Security), as those rules
    required. Each round's results are kept in results/morning_round*.json.</p>
    <p><b>Earlier: one habit changes.</b> Four kinds of unannounced change in how the team marks invoices in the tracker:
    the REVIEW cutoff moved from $5,000 to $10,000; the team stopped marking REVIEW; approvals moved from Mireille Ashdown
    (tag "REVIEW - MA") to Rosalind Quennell ("REVIEW - RQ"); REVIEW paused for six weeks and came back. Each kind comes at
    three doses: the tracker shows 1, 3 or 7 invoices handled the new way since the latest change, where the new and old
    habit disagree. Everything else in the company is identical across doses. All evidence is in the tracker the agent
    edits, so no score depends on whether an agent opens email. For "came back", a model that ignores dates also passes;
    that kind tests whether the pause makes a model drop the habit.</p>
    <p>In that earlier benchmark, on "habit stopped" Fable 5.2 noticed the change in all 15 tries but kept REVIEW to be safe; the answer key counted those as misses. <b>Score</b> there: for each try, the share of the four non-trivial test invoices that are logged exactly once with
    the team's current note (the tiny office-supply bill is left out: every version of the habit agrees on it). The
    model score is the mean over 12 versions × 5 tries, with a 95% bootstrap interval over tries. Pass@1 is the share
    of tries where every check holds, including bookkeeping.</p>
    <p><b>Shared agent.</b> The main benchmark and the earlier one-habit benchmark come from one plain agent loop, the same for all models: the same system
    prompt, a single tool that runs a bash command, reasoning effort "high", at most 80 steps, and no fallback to another
    model on refusal. Claude models are called through Anthropic's API, GPT models through OpenAI's. This keeps the
    comparison about the model, not the vendor's agent product.</p>
    <p><b>Earlier experiments</b> (ladder and levels tabs, and their options in the leaderboard dropdown) ran each model
    inside its own vendor's agent, Claude Code or Codex. They are kept for reference; they mix model and product.</p>
    <p><b>Ladder.</b> Six tasks, same company and the same five new invoices, no pointer in the instruction:
    (1) big invoices get REVIEW in the tracker's Notes; (2) same, but the cutoff moved from $5,000 to $10,000 in October;
    (3) same, but one supplier stopped getting REVIEW after signing a contract; (4) big invoices are emailed to the
    director for approval; (5) approvals with the cutoff change and the exempt supplier; (6) approvals, but the director
    is on leave and staff send them to a deputy, whose name only appears in those threads. Each task's history is
    generated from its rule, and each has a simpler rule that gives different answers on the test invoices.</p>
    <p><b>Mean Score</b> per task is the share of the five invoices where the agent made the team's call, zero if it never
    acted on the habit at all. The ladder score is the mean over the six tasks, per try. <b>Pass@1</b> is the share of
    task attempts where every check holds, including bookkeeping (each invoice logged once, past records untouched).
    Intervals: Mean Score, 95% bootstrap over tries (10,000 resamples); Pass@1, 95% Wilson. "±" shows half the
    interval's width.</p>
    <p><b>Levels.</b> For task 5 only: pointed (the instruction adds "handle these the way the team usually does"),
    rule written in an email among ~800 others, and rule told in the instruction. Every model passes every
    told attempt, so the task is fair.</p>
    <p><b>Company.</b> Background is 2,100 emails, Slack threads and tickets from the Redwood Inference corpus
    (EnterpriseRAG-Bench by Onyx, MIT), filtered so nothing contradicts or hints at a rule. The grader is deterministic:
    no model grades another.</p>
    <p><b>Infrastructure.</b> Each attempt runs in a fresh sandbox via Valkyrie on Modal. Logos from Simple Icons (CC0).</p>
  </section>
</div>
<footer><div class="wrap">PrecedentBench · Vals Hacks 2026 · built on Valkyrie</div></footer>
<div class="tip" hidden></div>
<script>
const t = new URLSearchParams(location.search).get("theme");
if (t) document.documentElement.dataset.theme = t;
const D = __DATA__;
const ICON = __ICONS__;
const levelSel = document.getElementById("level"), metricSel = document.getElementById("metric");
D.levels.forEach(([k, label]) => levelSel.add(new Option(label, k)));
const qp = new URLSearchParams(location.search);
if (qp.get("level")) levelSel.value = qp.get("level");
if (qp.get("metric")) metricSel.value = qp.get("metric");
if (qp.get("tab")) setTimeout(() => document.querySelector(`[data-tab="${qp.get("tab")}"]`).click());
const LAB = l => l === "Anthropic" ? "anthropic" : "openai";
const fmt = x => (x * 100).toFixed(1) + "%";
const pm = (lo, hi) => "±" + ((hi - lo) * 50).toFixed(1) + "%";
document.getElementById("quote").textContent = D.quote;

function rows() {
  const lv = levelSel.value, mt = metricSel.value;
  const list = Object.values(D.models).filter(m => m.levels[lv])
    .map(m => ({m, s: m.levels[lv][mt], d: m.levels[lv]}))
    .sort((a, b) => b.s[0] - a.s[0] || b.s[2] - a.s[2] || a.m.name.localeCompare(b.m.name));
  document.getElementById("rows").innerHTML = list.map(({m, s, d}) => {
    const [p, lo, hi] = s, c = LAB(m.lab);
    const why = Object.entries(d.fails || {}).map(([k, n]) => `${k} (${n})`).join(", ");
    const tip = [m.name + " · " + (d.agent || m.agent),
      `Mean Score ${fmt(d.rule[0])} (95%: ${fmt(d.rule[1])} to ${fmt(d.rule[2])})`,
      `Pass@1 ${d.k}/${d.n} = ${fmt(d.pass[0])} (95%: ${fmt(d.pass[1])} to ${fmt(d.pass[2])})`,
      why ? "Misses: " + why : ""].filter(Boolean).join("|");
    return `<div class="lrow" tabindex="0" data-tip="${tip.replace(/"/g, "&quot;")}">
      <div class="ltop"><span class="mname">${ICON[m.lab] || ""}${m.name}<span class="mtag">${d.agent || m.agent}</span></span>
        <span class="mscore mono">${fmt(p)}<span class="pm">${pm(lo, hi)}</span></span></div>
      <div class="lbar">
        <div class="fill" style="width:${Math.max(p * 100, .8)}%;background:linear-gradient(90deg,var(--${c}-a),var(--${c}-b))"></div>
        ${p > lo ? `<div class="lo" style="left:${lo * 100}%;width:${(p - lo) * 100}%;background:var(--${c}-c)"></div>` : ""}
        ${hi > p ? `<div class="wh" style="left:${p * 100}%;width:${(hi - p) * 100}%"></div>` : ""}
      </div>
    </div>`;
  }).join("");
  bindTips();
}
document.getElementById("axis").innerHTML = [0, 10, 20, 30, 40, 50, 60, 70, 80, 100].map(v => `<span style="left:${v}%">${v}%</span>`).join("");

const cellHtml = (v, sub) => {
  const bg = `color-mix(in oklab, #2a78d6 ${Math.round(v * 85)}%, var(--cell-0))`;
  const ink = v > .55 ? "#fff" : "var(--cell-ink)";
  return `<td><div class="cell mono" style="background:${bg};color:${ink}">${fmt(v)}<small>${sub}</small></div></td>`;
};
const notRun = "<td><div class='cell' style='background:var(--cell-0);color:var(--text-muted)'>not run</div></td>";
const nameCell = m => `<td class='nm'>${ICON[m.lab] || ""}${m.name}</td>`;

function lgrid() {
  const L = Object.values(D.models).filter(m => m.levels.ladder)
    .sort((a, b) => b.levels.ladder.rule[0] - a.levels.ladder.rule[0]);
  const head = "<tr><th></th>" + D.ladder.map(([t, l, w], i) =>
    `<th class="c">${i + 1}. ${l}<small>${w === "tracker" ? "in the spreadsheet" : "only in email"}</small></th>`).join("") +
    "<th class='c'>Overall<small>passed</small></th></tr>";
  document.getElementById("lgrid").innerHTML = head + L.map(m => {
    const d = m.levels.ladder;
    return "<tr>" + nameCell(m) + D.ladder.map(([t]) => d.tasks[t]
      ? cellHtml(d.tasks[t].score, `${d.tasks[t].k}/${d.tasks[t].n} passed`) : notRun).join("")
      + cellHtml(d.rule[0], `${d.runs} tries`) + "</tr>";
  }).join("");
}

function grid() {
  const hid = m => (m.levels.nudged ? m.levels.nudged.rule[0] : -1) + (m.levels.written ? m.levels.written.rule[0] / 10 : 0);
  const order = Object.values(D.models).filter(m => Object.keys(m.levels).length).sort((a, b) => hid(b) - hid(a));
  const lv = ["told", "written", "nudged"].map(k => D.levels.find(l => l[0] === k)).filter(Boolean);
  const head = "<tr><th></th>" + lv.map(([, l]) => `<th class="c">${l}</th>`).join("") + "</tr>";
  document.getElementById("grid").innerHTML = head + order.map(m => "<tr>" + nameCell(m) + lv.map(([k]) => {
    const d = m.levels[k];
    return d ? cellHtml(d.rule[0], `${d.k}/${d.n} passed`) : notRun;
  }).join("") + "</tr>").join("");
}

const DRIFT = () => Object.values(D.models).filter(m => m.levels.drift)
  .sort((a, b) => b.levels.drift.rule[0] - a.levels.drift.rule[0]);
// series color follows the model (fixed order), never its rank
const SERIES = m => "var(--s" + (D.order.filter(k => D.models[k] && D.models[k].levels.drift).indexOf(
  Object.keys(D.models).find(k => D.models[k] === m)) + 1) + ")";

function doseChart() {
  const M = DRIFT();
  if (!M.length) { document.getElementById("t-dose").innerHTML = "<p class='note'>Drift results not in yet.</p>"; return; }
  const W = 640, H = 320, pl = 44, pr = 92, pt = 14, pb = 34;
  const xs = D.drift.doses, X = i => pl + i * (W - pl - pr) / (xs.length - 1), Y = v => pt + (1 - v) * (H - pt - pb);
  let g = "";
  for (const v of [0, .25, .5, .75, 1]) g += `<line class="gl" x1="${pl}" x2="${W - pr}" y1="${Y(v)}" y2="${Y(v)}"/>` +
    `<text class="ax" x="${pl - 8}" y="${Y(v) + 4}" text-anchor="end">${v * 100}%</text>`;
  xs.forEach((d, i) => { g += `<text class="ax" x="${X(i)}" y="${H - 12}" text-anchor="middle">${d} example${d > 1 ? "s" : ""}</text>`; });
  const ends = [];
  for (const m of M) {
    const c = SERIES(m), pts = xs.map((d, i) => [X(i), Y(m.levels.drift.dose[d][0]), d, m.levels.drift.dose[d]]);
    g += `<polyline class="ln" stroke="${c}" points="${pts.map(p => p[0] + "," + p[1]).join(" ")}"/>`;
    for (const [x, y, d, v] of pts) {
      const tip = `${m.name}|${d} example${d > 1 ? "s" : ""} after the change|Score ${fmt(v[0])} (95%: ${fmt(v[1])} to ${fmt(v[2])})`;
      g += `<circle class="pt" cx="${x}" cy="${y}" r="5" fill="${c}"/><circle class="hit dpt" cx="${x}" cy="${y}" r="12" data-tip="${tip}"/>`;
    }
    ends.push([pts[pts.length - 1][1], m]);
  }
  // direct end labels only where they don't collide; the legend always carries identity
  ends.sort((a, b) => a[0] - b[0]);
  let last = -99;
  for (const [y, m] of ends) { if (y - last >= 15) { g += `<text class="lab" x="${W - pr + 10}" y="${y + 4}">${m.name}</text>`; last = y; } }
  document.getElementById("dose").innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Score by number of examples after the change, one line per model">${g}</svg>`;
  document.getElementById("dleg").innerHTML = M.map(m =>
    `<li><i style="background:${SERIES(m)}"></i>${m.name}<span class="v">${fmt(m.levels.drift.rule[0])}</span></li>`).join("");
  document.querySelectorAll(".dpt").forEach(el => {
    el.onmousemove = e => { const [t1, ...ls] = el.dataset.tip.split("|"); tip.innerHTML = "<b>" + t1 + "</b>" + ls.join("<br>");
      tip.hidden = false; tip.style.left = Math.min(e.clientX + 14, innerWidth - tip.offsetWidth - 8) + "px"; tip.style.top = (e.clientY + 14) + "px"; };
    el.onmouseleave = () => tip.hidden = true;
  });
}

function kgrid() {
  const M = DRIFT();
  if (!M.length) return;
  const head = "<tr><th></th>" + D.drift.types.map(([k, l, w]) => `<th class="c">${l}<small>${w}</small></th>`).join("") +
    "<th class='c'>Overall</th></tr>";
  const body = M.map(m => { const d = m.levels.drift;
    return "<tr>" + nameCell(m) + D.drift.types.map(([k]) => {
      const cs = D.drift.doses.map(x => d.cells[k + "-" + x]).filter(Boolean);
      if (!cs.length) return notRun;
      const sub = D.drift.doses.map(x => { const c = d.cells[k + "-" + x]; return c ? Math.round(c.score * 100) : "–"; }).join(" · ");
      return cellHtml(d.kind[k], D.drift.doses.join(" · ") + " ex: " + sub);
    }).join("") + cellHtml(d.rule[0], d.k + "/" + d.n) + "</tr>"; }).join("");
  document.getElementById("kgrid").innerHTML = head + body;
  const hes = M.map(m => [m.name, ((m.levels.drift.fails_by_type || {}).returned || {})["left blank, asked"] || 0,
    D.drift.doses.reduce((s, x) => s + ((m.levels.drift.cells["returned-" + x] || {}).n || 0), 0)]).filter(x => x[1] > 0);
  document.getElementById("hes-note").innerHTML = hes.length ? '<b>About "habit came back".</b> ' +
    hes.map(([n, c, t]) => `${n} left the notes blank and asked in ${c} of ${t} tries`).join("; ") +
    ". In those tries the agent read that REVIEW was back on recent invoices but would not apply it without being told, so the answer key counts a miss." : "";
}

function hbgrid() {
  const M = DRIFT().filter(m => m.levels.drift.hb && m.levels.drift.hb.yes);
  if (!M.length) return;
  const head = "<tr><th></th><th class='c'>Without the handbook<small>2 and 3 examples</small></th>" +
    "<th class='c'>With the stale handbook<small>2 and 3 examples</small></th><th class='c'>Followed the handbook<small>tries</small></th></tr>";
  document.getElementById("hbgrid").innerHTML = head + M.map(m => { const h = m.levels.drift.hb;
    return "<tr>" + nameCell(m) + cellHtml(h.no[0], "±" + ((h.no[2] - h.no[1]) * 50).toFixed(0) + "%") +
      cellHtml(h.yes[0], "±" + ((h.yes[2] - h.yes[1]) * 50).toFixed(0) + "%") +
      `<td><div class="cell mono" style="background:var(--cell-0);color:var(--cell-ink)">${h.followed} of ${h.n}</div></td></tr>`; }).join("");
}

function ptable() {
  const order = Object.values(D.models).sort((a, b) =>
    ((b.levels.drift || b.levels.ladder || {rule: [-1]}).rule[0]) - ((a.levels.drift || a.levels.ladder || {rule: [-1]}).rule[0]));
  const cols = D.levels.map(([k, l]) => [k, l]);
  const head = "<tr><th>Model</th><th>Agent</th>" + cols.map(([, l]) => `<th>${l}</th>`).join("") + "</tr>";
  document.getElementById("ptable").innerHTML = head + order.map(m => `<tr><td>${m.name}</td><td>${m.agent} / shared</td>` +
    cols.map(([k]) => { const d = m.levels[k]; return `<td class="mono">${d ? fmt(d.rule[0]) + " · " + d.k + "/" + d.n : "–"}</td>`; }).join("") +
    "</tr>").join("");
}

function takeaways() {
  const M = Object.values(D.models);
  const items = [];
  const Dm = DRIFT();
  if (Dm.length) {
    const top = Dm[0], bot = Dm[Dm.length - 1];
    const zero = Dm.filter(m => m.levels.drift.rule[0] === 0).map(m => m.name);
    items.push([`${top.name} leads at ${fmt(top.levels.drift.rule[0])}; ${bot.name} trails at ${fmt(bot.levels.drift.rule[0])}`,
      (zero.length ? `${zero.join(", ")} score${zero.length > 1 ? "" : "s"} zero overall. ` : "Every model scores above zero. ") +
      "Same agent, same instructions, same tool for every model: the gap is the model."]);
    const lo = D.drift.doses[0], hiD = D.drift.doses[D.drift.doses.length - 1];
    const d1 = Dm.reduce((s, m) => s + m.levels.drift.dose[lo][0], 0) / Dm.length;
    const d7 = Dm.reduce((s, m) => s + m.levels.drift.dose[hiD][0], 0) / Dm.length;
    const H = Dm.filter(m => m.levels.drift.hb && m.levels.drift.hb.yes);
    if (H.length) {
      const no = H.reduce((s, m) => s + m.levels.drift.hb.no[0], 0) / H.length, yes = H.reduce((s, m) => s + m.levels.drift.hb.yes[0], 0) / H.length;
      const fol = H.reduce((s, m) => s + m.levels.drift.hb.followed, 0), tot = H.reduce((s, m) => s + m.levels.drift.hb.n, 0);
      items.push(["A stale handbook makes every model worse",
        `With 2 or 3 examples of the new habits, the average score is ${fmt(no)} without the old AP policy in the shared drive and ${fmt(yes)} with it. ` +
        `In ${fol} of ${tot} tries with the handbook, the agent followed the written policy over what the team actually does.`]);
    }
    items.push(["Models need repeated evidence before they notice a change",
      `Without the handbook, the average score is ${fmt(d1)} when the tracker shows ${lo} invoice${lo > 1 ? "s" : ""} per new habit and ${fmt(d7)} with ${hiD}.`]);
    const kinds = D.drift.types.map(([k, l]) => [l, Dm.reduce((s, m) => s + (m.levels.drift.kind[k] || 0), 0) / Dm.length]).sort((a, b) => a[1] - b[1]);
    items.push([`Hardest habit: ${kinds[0][0].toLowerCase()}`,
      `Share of each habit's invoices right, averaged over models (no handbook): ${kinds.map(([l, v]) => `${l.toLowerCase()} ${fmt(v)}`).join(", ")}.`]);
    document.getElementById("tk").innerHTML = items.map(([b, s]) => `<li><b>${b}</b><span>${s}</span></li>`).join("");
    return;   // earlier (vendor-agent) takeaways only show when there are no drift results
  }
  const L = M.filter(m => m.levels.ladder).sort((a, b) => b.levels.ladder.rule[0] - a.levels.ladder.rule[0]);
  if (L.length) {
    const zero = L.filter(m => m.levels.ladder.rule[0] === 0).map(m => m.name);
    items.push([`${L[0].name} leads the ladder at ${fmt(L[0].levels.ladder.rule[0])}; ${L[L.length - 1].name} trails at ${fmt(L[L.length - 1].levels.ladder.rule[0])}`,
      (zero.length ? `${zero.join(", ")} score${zero.length > 1 ? "" : "s"} zero overall. ` : "Every model scores above zero overall. ") +
      "The spread comes from the hard tasks: the easy ones are solved by everyone."]);
    const part = (m, w) => { const ts = D.ladder.filter(x => x[2] === w).map(x => m.levels.ladder.tasks[x[0]]).filter(Boolean);
      return ts.reduce((s, x) => s + x.score, 0) / ts.length; };
    const sheet = L.reduce((s, m) => s + part(m, "tracker"), 0) / L.length;
    const mail = L.reduce((s, m) => s + part(m, "email"), 0) / L.length;
    const lookers = L.filter(m => part(m, "email") > .5).map(m => m.name);
    items.push(["If the habit isn't in the file they edit, most agents never find it",
      `Across models, the average score is ${fmt(sheet)} when the habit shows in the spreadsheet and ${fmt(mail)} when it only shows in email. ` +
      (lookers.length ? `Only ${lookers.join(" and ")} score above 50% on the email tasks.` : "No model scores above 50% on the email tasks.")]);
  }
  const N = M.filter(m => m.levels.nudged);
  if (N.length) {
    const old = N.reduce((s, m) => s + (m.levels.nudged.fails["used the old $5k rule"] || 0), 0);
    const miss = N.reduce((s, m) => s + (m.levels.nudged.n - m.levels.nudged.k), 0);
    items.push(["Finding the habit is not the same as getting it right",
      `Told to handle invoices "the way the team usually does", every model finds the approval habit. Of ${miss} failed attempts, ` +
      `${old} applied the old $5,000 cutoff: they learned the habit but missed that it changed.`]);
  }
  const told = M.filter(m => m.levels.told);
  if (told.length) {
    const att = told.reduce((s, m) => s + m.levels.told.n, 0), passed = told.reduce((s, m) => s + m.levels.told.k, 0);
    items.push(["Told the rule, every model follows it",
      `${passed} of ${att} attempts pass when the rule is in the instruction. The gap between that and the ladder is the cost of rules nobody wrote down.`]);
  }
  document.getElementById("tk").innerHTML = items.map(([b, s]) => `<li><b>${b}</b><span>${s}</span></li>`).join("");
}

const tip = document.querySelector(".tip");
function bindTips() {
  document.querySelectorAll(".lrow").forEach(row => {
    const show = (x, y) => {
      const [title, ...lines] = row.dataset.tip.split("|");
      tip.innerHTML = "<b>" + title + "</b>" + lines.join("<br>");
      tip.hidden = false;
      tip.style.left = Math.min(x + 14, innerWidth - tip.offsetWidth - 8) + "px";
      tip.style.top = (y + 14) + "px";
    };
    row.onmousemove = e => show(e.clientX, e.clientY);
    row.onmouseleave = () => tip.hidden = true;
    row.onfocus = () => { const r = row.getBoundingClientRect(); show(r.left + 30, r.bottom); };
    row.onblur = () => tip.hidden = true;
  });
}
document.querySelectorAll(".tabs button").forEach(b => b.onclick = () => {
  document.querySelectorAll(".tabs button").forEach(x => x.setAttribute("aria-selected", x === b));
  ["t-dose", "t-kind", "t-hb", "t-ladder", "t-levels", "t-table"].forEach(id => document.getElementById(id).hidden = id !== b.dataset.tab);
});
levelSel.onchange = rows; metricSel.onchange = rows;
rows(); doseChart(); kgrid(); hbgrid(); lgrid(); grid(); ptable(); takeaways();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    data = summarize(json.loads((HERE / "v3_attempts.json").read_text()))
    if (HERE / "drift_attempts.json").exists():
        summarize_drift(data, json.loads((HERE / "drift_attempts.json").read_text()))
    rounds = sorted(HERE.glob("morning_round*.json"))
    if rounds:    # the latest round is the main benchmark; earlier rounds stay in their own files
        summarize_morning(data, json.loads(rounds[-1].read_text()))
    if (HERE / "ladder_attempts.json").exists():
        summarize_ladder(data, json.loads((HERE / "ladder_attempts.json").read_text()))
    (HERE / "leaderboard.html").write_text(page(data))
    for m in data.values():
        print(m["name"].ljust(12), "  ".join(
            f"{k}: {v['rule'][0]*100:5.1f}% pass {v['k']}/{v['n']}" for k, v in m["levels"].items()))
