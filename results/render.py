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
LEVELS = [("nudged", "Pointed at past work, rule unstated"), ("hidden", "Rule only in past work, no pointer"),
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
FABLE_QUOTE = ("There is no written approval policy in the company files, so I inferred the rule "
               "from past practice in the tracker and mail archive.")


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


def page(data: dict) -> str:
    attempts = sorted({lv["n"] for m in data.values() for lv in m["levels"].values()})
    top = max((m["levels"]["nudged"]["rule"][0], m["name"]) for m in data.values() if "nudged" in m["levels"])
    att_txt = str(attempts[-1]) if len(attempts) == 1 else f"{attempts[0]}–{attempts[-1]}"
    blob = json.dumps({"models": data, "levels": LEVELS, "quote": FABLE_QUOTE})
    return (TEMPLATE.replace("__DATA__", blob).replace("__N_MODELS__", str(len(data)))
            .replace("__ATTEMPTS__", att_txt).replace("__TOP__", f"{top[0] * 100:.1f}%"))


TEMPLATE = r"""<!doctype html>
<html lang="en" class="viz-root">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PrecedentBench: can AI agents follow the rules nobody wrote down?</title>
<style>
.viz-root {
  color-scheme: light;
  --surface-1: #ffffff; --surface-2: #f6f6f4; --card: #ffffff; --line: #e8e8e5; --track: #f1f1ef;
  --text-primary: #0b0b0b; --text-secondary: #52514e; --text-muted: #8a8984;
  --anthropic-a: #f3a27b; --anthropic-b: #eb6834; --anthropic-c: #c4501f;
  --openai-a: #7dd8b6; --openai-b: #1baf7a; --openai-c: #128a5f;
  --whisker: #9a9993; --cell-0: #f1f1ef; --cell-ink: #0b0b0b;
}
@media (prefers-color-scheme: dark) {
  :root:where(:not([data-theme="light"])).viz-root {
    color-scheme: dark;
    --surface-1: #141413; --surface-2: #1d1d1b; --card: #1a1a19; --line: #2e2e2b; --track: #262624;
    --text-primary: #f0efec; --text-secondary: #c3c2b7; --text-muted: #8e8d86;
    --anthropic-a: #b9532a; --anthropic-b: #d95926; --anthropic-c: #f08a5d;
    --openai-a: #11704e; --openai-b: #199e70; --openai-c: #4cc795;
    --whisker: #77766f; --cell-0: #262624; --cell-ink: #f0efec;
  }
}
:root[data-theme="dark"].viz-root {
  color-scheme: dark;
  --surface-1: #141413; --surface-2: #1d1d1b; --card: #1a1a19; --line: #2e2e2b; --track: #262624;
  --text-primary: #f0efec; --text-secondary: #c3c2b7; --text-muted: #8e8d86;
  --anthropic-a: #b9532a; --anthropic-b: #d95926; --anthropic-c: #f08a5d;
  --openai-a: #11704e; --openai-b: #199e70; --openai-c: #4cc795;
  --whisker: #77766f; --cell-0: #262624; --cell-ink: #f0efec;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--surface-1); color: var(--text-primary);
  font: 15px/1.55 Inter, ui-sans-serif, -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; }
.mono { font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; font-variant-numeric: tabular-nums; }
.wrap { max-width: 1140px; margin: 0 auto; padding: 0 40px; }
.crumbs { font-size: 12px; color: var(--text-muted); padding: 18px 0; border-bottom: 1px solid var(--line); }
.crumbs b { color: var(--text-primary); font-weight: 500; }
.hero { text-align: center; padding: 72px 0 56px; }
.hero h1 { font-size: 46px; line-height: 1.12; font-weight: 500; letter-spacing: -.02em; margin: 0 0 14px; }
.hero .with { color: var(--text-muted); font-size: 13px; margin-bottom: 18px; }
.hero p { color: var(--text-secondary); max-width: 640px; margin: 0 auto 26px; }
.btns { display: flex; gap: 10px; justify-content: center; }
.btn { font: inherit; font-size: 13px; padding: 9px 18px; border-radius: 6px; text-decoration: none;
  background: var(--surface-2); color: var(--text-primary); border: 1px solid var(--line); }
.btn.primary { background: #4f46e5; color: #fff; border-color: #4f46e5; }
.stats { display: grid; grid-template-columns: repeat(4, 1fr); padding: 34px 0 70px; }
.stat { text-align: center; border-left: 1px solid var(--line); }
.stat:first-child { border-left: 0; }
.stat .v { font-size: 44px; font-weight: 400; letter-spacing: -.02em; line-height: 1.1; }
.stat .k { color: var(--text-muted); font-size: 17px; }
.lb { display: grid; grid-template-columns: 1fr 1.05fr; gap: 56px; align-items: start; padding-bottom: 90px; }
.lb h2, .sec h2 { font-size: 22px; font-weight: 500; margin: 0 0 18px; }
.lb .copy p { color: var(--text-secondary); margin: 0 0 16px; }
.chips { display: flex; gap: 8px; margin-top: 22px; }
.chips a { font-size: 13px; background: var(--surface-2); border: 1px solid var(--line); border-radius: 6px;
  padding: 5px 11px; color: var(--text-primary); text-decoration: none; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 26px 26px 20px; }
.card-head { display: flex; justify-content: space-between; color: var(--text-muted); font-size: 13px; margin-bottom: 6px; }
.lrow { padding: 10px 6px 6px; margin: 0 -6px; outline: none; border-radius: 6px; }
.lrow:hover, .lrow:focus-visible { background: var(--surface-2); }
.ltop { display: flex; justify-content: space-between; align-items: baseline; gap: 10px; }
.mname { font-size: 16px; font-weight: 500; display: flex; align-items: center; gap: 7px; }
.mark { width: 12px; height: 12px; border-radius: 3px; display: inline-block; }
.mtag { color: var(--text-muted); font-size: 12px; font-weight: 400; }
.mscore { font-size: 14px; white-space: nowrap; }
.mscore .ci { color: var(--text-muted); font-size: 12px; margin-left: 6px; }
.lbar { position: relative; height: 6px; margin-top: 9px; background: var(--track); border-radius: 3px; }
.lbar .fill { position: absolute; left: 0; top: 0; bottom: 0; border-radius: 3px; }
.lbar .lo { position: absolute; top: 0; bottom: 0; border-radius: 0 3px 3px 0; }
.lbar .wh { position: absolute; top: 50%; height: 1px; background: var(--whisker); }
.lbar .wh::after { content: ""; position: absolute; right: -1px; top: -3px; width: 1px; height: 7px; background: var(--whisker); }
.why { color: var(--text-muted); font-size: 12px; margin-top: 5px; min-height: 18px; }
.axis { position: relative; height: 22px; margin-top: 18px; border-top: 1px solid var(--line); }
.axis span { position: absolute; top: 6px; transform: translateX(-50%); color: var(--text-muted); font-size: 11px; }
.axis span:first-child { transform: none; }
.axis span:last-child { transform: translateX(-100%); }
.card-foot { display: flex; justify-content: space-between; align-items: center; margin-top: 18px; gap: 12px; flex-wrap: wrap; }
select { font: inherit; font-size: 13px; color: var(--text-primary); background: var(--card);
  border: 1px solid var(--line); border-radius: 6px; padding: 5px 8px; }
.sec { padding: 0 0 80px; }
.takeaways { list-style: none; padding: 0; margin: 0; max-width: 760px; counter-reset: t; }
.takeaways li { counter-increment: t; padding: 16px 0 16px 34px; border-bottom: 1px solid var(--line); position: relative; }
.takeaways li::before { content: counter(t); position: absolute; left: 6px; top: 16px; color: #4f46e5; }
.takeaways b { display: block; font-weight: 500; font-size: 16px; margin-bottom: 3px; }
.takeaways span { color: var(--text-secondary); font-size: 14px; }
.grid { width: 100%; border-collapse: separate; border-spacing: 2px; }
.grid th { color: var(--text-muted); font-weight: 400; font-size: 13px; text-align: left; padding: 8px 10px; }
.grid th.c { text-align: center; }
.grid td { padding: 0; }
.grid td.nm { padding: 0 14px 0 4px; white-space: nowrap; font-weight: 500; }
.cell { height: 46px; border-radius: 4px; display: flex; flex-direction: column; align-items: center; justify-content: center;
  font-size: 14px; }
.cell small { font-size: 11px; opacity: .8; }
.sub { color: var(--text-secondary); margin: -8px 0 22px; max-width: 760px; }
.method { color: var(--text-secondary); font-size: 14px; max-width: 820px; }
.method p { margin: 0 0 12px; }
.method b { color: var(--text-primary); font-weight: 500; }
.tip { position: fixed; pointer-events: none; background: var(--text-primary); color: var(--surface-1);
  font-size: 12.5px; padding: 9px 11px; border-radius: 8px; max-width: 300px; line-height: 1.45; z-index: 9; }
.tip b { display: block; margin-bottom: 3px; }
[hidden] { display: none !important; }
@media (max-width: 900px) {
  .lb { grid-template-columns: 1fr; }
  .stats { grid-template-columns: repeat(2, 1fr); row-gap: 24px; }
  .hero h1 { font-size: 34px; }
}
</style>
</head>
<body>
<div class="wrap">
  <div class="crumbs">Vals Hacks 2026 › Build your own eval › <b>PrecedentBench</b></div>

  <section class="hero">
    <h1>Can AI agents follow the rules<br>nobody wrote down?</h1>
    <div class="with">PrecedentBench · built on Valkyrie, run on Modal</div>
    <p>Every company runs on habits that live in past work, not in a handbook. PrecedentBench drops an agent
    into a company's finance team and checks whether it does the job the way this team does it, using only
    what the team did before.</p>
    <div class="btns"><a class="btn primary" href="#leaderboard">See the leaderboard</a><a class="btn" href="#method">Read methodology</a></div>
  </section>

  <section class="stats">
    <div class="stat"><div class="v">__N_MODELS__</div><div class="k">Frontier models</div></div>
    <div class="stat"><div class="v">4</div><div class="k">Levels of hidden</div></div>
    <div class="stat"><div class="v">__ATTEMPTS__</div><div class="k">Attempts per level</div></div>
    <div class="stat"><div class="v">__TOP__</div><div class="k">Top rule score, pointed</div></div>
  </section>

  <section class="lb" id="leaderboard">
    <div class="copy">
      <h2>The PrecedentBench leaderboard</h2>
      <p>The agent joins Redwood Inference's finance team. Five supplier invoices just came in, and three months
      of company email, Slack and tickets sit in its workspace. The request is one line: log the invoices.</p>
      <p>The catch: big invoices need the finance director's approval first, the cutoff quietly moved from $5,000
      to $10,000 in October, and one supplier stopped needing approval after signing a contract. None of it is
      written down. It only shows in how the team handled the last 90 invoices.</p>
      <p>Each model runs the same task four ways. The headline level points the agent at the team's history
      ("handle these the way the team usually does") without stating any rule, so it measures whether the agent can
      work the rule out. The others remove that pointer, write the rule in an email, or state it outright. That last
      one is the fairness check.</p>
      <div class="chips"><a href="#ladder">Where it breaks</a><a href="#takeaways">Takeaways</a><a href="#method">Methodology</a></div>
    </div>
    <div class="card">
      <div class="card-head"><span>Model</span><span id="metric-label">Score</span></div>
      <div id="rows"></div>
      <div class="axis" id="axis"></div>
      <div class="card-foot">
        <select id="level" aria-label="Level"></select>
        <select id="metric" aria-label="Metric">
          <option value="rule">Rule score</option>
          <option value="pass">Pass rate</option>
        </select>
      </div>
    </div>
  </section>

  <section class="sec" id="takeaways">
    <h2>Key takeaways</h2>
    <ol class="takeaways" id="tk"></ol>
  </section>

  <section class="sec" id="ladder">
    <h2>Where it breaks</h2>
    <p class="sub">Rule score per model as the rule gets harder to find. Same company, same invoices, same checks;
    only where the rule lives changes.</p>
    <table class="grid" id="grid"></table>
  </section>

  <section class="sec method" id="method">
    <h2>Methodology</h2>
    <p><b>Task.</b> Log five new supplier invoices. One ($13,960) needs the director's approval. Two ($7,280 and
    $6,925) are under the new $10,000 cutoff. One ($11,340.50) is from the exempt supplier, and one is a small office
    supply bill. The $6,925 one comes from a supplier whose last large invoice did go for approval, so copying the
    last case for that supplier gets it wrong.</p>
    <p><b>Rule score</b> is the share of the rule's three parts an attempt got right: (1) asked the director about the
    one invoice that needs it, (2) left the two invoices under $10,000 alone, (3) left the exempt supplier alone.
    Parts 2 and 3 only count when part 1 holds, so asking nobody earns nothing. <b>Pass rate</b> is the share of
    attempts where every check holds, including bookkeeping (each invoice logged once, past records untouched).</p>
    <p><b>Levels.</b> Pointed: the instruction adds "The team's email, Slack and tickets are in /app/company/. Handle
    these the way the team usually does." No pointer: the same task without that line. In an email: three emails from
    the director state the rules among ~800 others. Told: the rules are in the instruction. The company, invoices and
    checks are identical across levels. The pointed level has 3 attempts per model so far; the others have 8.</p>
    <p><b>Intervals.</b> Rule score: 95% bootstrap over attempts, 10,000 resamples. Pass rate: 95% Wilson interval.
    Attempt counts are small, so intervals are wide. When every attempt scores zero the bootstrap range collapses to
    zero; the pass-rate interval (0 to 32% for 0 of 8) is the honest bound there.</p>
    <p><b>Company.</b> Background is 2,100 emails, Slack threads and tickets from the Redwood Inference corpus
    (EnterpriseRAG-Bench by Onyx, MIT), filtered so nothing contradicts or hints at the rule. The finance history
    (90 invoices, every supplier email, 16 approval threads) is generated from the rule itself, so it can't
    disagree with the answer key.</p>
    <p><b>Agents.</b> Claude models run in Claude Code, GPT models in Codex, each attempt in a fresh sandbox, via
    Valkyrie on Modal. The grader is deterministic: no model grades another.</p>
  </section>
</div>
<div class="tip" hidden></div>
<script>
const t = new URLSearchParams(location.search).get("theme");
if (t) document.documentElement.dataset.theme = t;
const D = __DATA__;
const levelSel = document.getElementById("level"), metricSel = document.getElementById("metric");
D.levels.forEach(([k, label]) => levelSel.add(new Option(label, k)));
const qp = new URLSearchParams(location.search);
if (qp.get("level")) levelSel.value = qp.get("level");
if (qp.get("metric")) metricSel.value = qp.get("metric");
const LAB = l => l === "Anthropic" ? "anthropic" : "openai";
const fmt = x => (x * 100).toFixed(1) + "%";

function rows() {
  const lv = levelSel.value, mt = metricSel.value;
  document.getElementById("metric-label").textContent = mt === "rule" ? "Rule score" : "Pass rate";
  const list = Object.values(D.models).filter(m => m.levels[lv])
    .map(m => ({m, s: m.levels[lv][mt], d: m.levels[lv]}))
    .sort((a, b) => b.s[0] - a.s[0] || b.s[2] - a.s[2] || a.m.name.localeCompare(b.m.name));
  document.getElementById("rows").innerHTML = list.map(({m, s, d}) => {
    const [p, lo, hi] = s, c = LAB(m.lab);
    const why = Object.entries(d.fails).map(([k, n]) => `${k} (${n})`).join(", ");
    const tip = [m.name + " · " + m.agent,
      `Rule score ${fmt(d.rule[0])} (95%: ${fmt(d.rule[1])}–${fmt(d.rule[2])})`,
      `Pass rate ${d.k}/${d.n} = ${fmt(d.pass[0])} (95%: ${fmt(d.pass[1])}–${fmt(d.pass[2])})`,
      why ? "Misses: " + why : "No misses"].join("|");
    return `<div class="lrow" tabindex="0" data-tip="${tip.replace(/"/g, "&quot;")}">
      <div class="ltop"><span class="mname"><i class="mark" style="background:var(--${c}-b)"></i>${m.name}
        <span class="mtag">${m.agent}</span></span>
        <span class="mscore mono">${fmt(p)}<span class="ci">${fmt(lo)}–${fmt(hi)}</span></span></div>
      <div class="lbar">
        <div class="fill" style="width:${Math.max(p * 100, .8)}%;background:linear-gradient(90deg,var(--${c}-a),var(--${c}-b))"></div>
        ${p > lo ? `<div class="lo" style="left:${lo * 100}%;width:${(p - lo) * 100}%;background:var(--${c}-c)"></div>` : ""}
        ${hi > p ? `<div class="wh" style="left:${p * 100}%;width:${(hi - p) * 100}%"></div>` : ""}
      </div>
      <div class="why">${why ? "Misses: " + why : "&nbsp;"}</div>
    </div>`;
  }).join("");
  bindTips();
}

document.getElementById("axis").innerHTML = [0, 20, 40, 60, 80, 100].map(v => `<span style="left:${v}%">${v}%</span>`).join("");

function grid() {
  const hid = m => (m.levels.hidden ? m.levels.hidden.rule[0] : 0);
  const order = Object.values(D.models).sort((a, b) => hid(b) - hid(a) || a.name.localeCompare(b.name));
  const lv = ["told", "written", "nudged", "hidden"].map(k => D.levels.find(l => l[0] === k));
  const head = "<tr><th></th>" + lv.map(([, l]) => `<th class="c">${l}</th>`).join("") + "</tr>";
  const body = order.map(m => "<tr><td class='nm'>" + m.name + "</td>" + lv.map(([k]) => {
    const d = m.levels[k];
    if (!d) return "<td><div class='cell' style='background:var(--cell-0);color:var(--text-muted)'>not run</div></td>";
    const v = d.rule[0];
    const bg = `color-mix(in oklab, #2a78d6 ${Math.round(v * 85)}%, var(--cell-0))`;
    const ink = v > .55 ? "#fff" : "var(--cell-ink)";
    return `<td><div class="cell mono" style="background:${bg};color:${ink}">${fmt(v)}<small>${d.k}/${d.n} passed</small></div></td>`;
  }).join("") + "</tr>").join("");
  document.getElementById("grid").innerHTML = head + body;
}

function takeaways() {
  const M = Object.values(D.models);
  const H = M.filter(m => m.levels.hidden);
  const best = H.reduce((a, b) => (b.levels.hidden.rule[0] > a.levels.hidden.rule[0] ? b : a));
  const never = H.filter(m => (m.levels.hidden.fails["never asked for approval"] || 0) === m.levels.hidden.n).length;
  const N = M.filter(m => m.levels.nudged).sort((a, b) => b.levels.nudged.rule[0] - a.levels.nudged.rule[0]);
  const items = [];
  if (N.length) {
    const old = N.reduce((s, m) => s + (m.levels.nudged.fails["used the old $5k rule"] || 0), 0);
    const miss = N.reduce((s, m) => s + (m.levels.nudged.n - m.levels.nudged.k), 0);
    items.push(["Pointed at the history, every model finds the habit, few get it right",
      `With one line telling it to handle invoices the way the team usually does, every attempt by every model asks the director for approval. ` +
      `${N[0].name} leads at ${fmt(N[0].levels.nudged.rule[0])}. Of ${miss} failed attempts, ${old} applied the old $5,000 cutoff: ` +
      "they learned the habit but not that it changed."]);
  }
  items.push([`Without the pointer, only ${best.name} reliably works out the unwritten rule`,
    `It reaches a ${fmt(best.levels.hidden.rule[0])} rule score when the rule lives only in past work. ` +
    `In its own words: "${D.quote}"`]);
  items.push([`${never} of ${H.length} models never ask for approval at all`,
    "Asked to log five invoices, they log all five and stop. In the runs we read, Sonnet and Haiku never open the " +
    "company history. The GPT models do search it, but for a written procedure (\"invoice tracker\", \"log invoices\"); " +
    "finding none, they log everything. One GPT-6.1 Sol run had the approval threads in its search results and never opened them. " +
    "Told the rule in the instruction, all of them follow it."]);
  const opus = M.find(m => m.name === "Opus 5.5");
  if (opus && opus.levels.hidden) {
    const f = opus.levels.hidden.fails, wrong = (f["used the old $5k rule"] || 0) + (f["missed the Halverson exception"] || 0) + (f["missed the $10k change"] || 0);
    items.push(["Finding the habit is not the same as getting it right",
      `In ${wrong} of ${opus.levels.hidden.n} attempts Opus 5.5 found the approval threads and still got the rule wrong, ` +
      "mostly by applying the old $5,000 cutoff to everything. Rule changes and exceptions are where precedent reasoning breaks."]);
  }
  const told = M.filter(m => m.levels.told);
  if (told.length) {
    const all = told.filter(m => m.levels.told.k === m.levels.told.n).length;
    const att = told.reduce((s, m) => s + m.levels.told.n, 0), passed = told.reduce((s, m) => s + m.levels.told.k, 0);
    items.push(["Told the rule, every model follows it",
      `${all} of ${told.length} models pass every attempt when the rule is in the instruction (${passed} of ${att} attempts overall), ` +
      "so the task itself is fair. " +
      "The gap between that and the hidden version is the cost of rules nobody wrote down."]);
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
levelSel.onchange = rows; metricSel.onchange = rows;
rows(); grid(); takeaways();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    data = summarize(json.loads((HERE / "v3_attempts.json").read_text()))
    (HERE / "leaderboard.html").write_text(page(data))
    for m in data.values():
        print(m["name"].ljust(12), "  ".join(
            f"{k}: rule {v['rule'][0]*100:5.1f}% pass {v['k']}/{v['n']}" for k, v in m["levels"].items()))
