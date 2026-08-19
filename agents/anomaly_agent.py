"""Anomaly Detection Agent.

Trigger: the traffic generator (see orchestrator.py) appends new rounds to
outcomes.jsonl. Every tick this agent looks at whatever new rows landed for
each (player_strategy, dealer_strategy) pairing and checks player bust/win
rate against fixed bounds.

The bounds aren't arbitrary: a 3000-round calibration run of the two
strategy pairs that actually exist in this repo gave

    standard_17 vs standard_17   -> 27.3% player bust, 41.5% player win
    aggressive_20 vs standard_17 -> 62.1% player bust, 29.7% player win

so "bust rate > 40%" or "win rate outside [30%, 55%]" comfortably separates
ordinary sampling variance from something structurally off, for this game.

Action: on a breach, one LLM call is given the stats plus the relevant
source (table.py, strategies.py, hand.py) and asked to produce a structured
incident report, which is written to agents/reports/ and committed.
"""
import json
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field
from strands import Agent

from agents.common import REPO_ROOT, git_commit, load_state, log, make_model, save_state

AGENT_NAME = "AnomalyDetectionAgent"
AUTHOR = ("Anomaly Detection Agent", "agent-anomaly@casino.local")
OUTCOMES_PATH = REPO_ROOT / "outcomes.jsonl"
REPORTS_DIR = REPO_ROOT / "agents" / "reports"

BATCH_SIZE = 40
BUST_CEILING = 0.40
WIN_RATE_RANGE = (0.30, 0.55)
COOLDOWN_SECONDS = 180


class IncidentReport(BaseModel):
    title: str = Field(description="Short incident title")
    severity: str = Field(description="one of: low, medium, high")
    likely_cause: str = Field(
        description="Best hypothesis for the root cause, grounded in the given source code"
    )
    evidence: str = Field(description="The specific stats/thresholds that were breached")
    recommendation: str = Field(description="A concrete next step for a human engineer")


def _read_new_rows(offset: int):
    if not OUTCOMES_PATH.exists():
        return [], offset
    lines = OUTCOMES_PATH.read_text().splitlines()
    new_lines = lines[offset:]
    return [json.loads(line) for line in new_lines if line.strip()], len(lines)


def tick():
    state = load_state()
    a_state = state.setdefault("anomaly_agent", {"offset": 0, "last_reported": {}})
    rows, new_offset = _read_new_rows(a_state["offset"])
    a_state["offset"] = new_offset

    if not rows:
        log(AGENT_NAME, "no new outcomes since last check. No action.")
        save_state(state)
        return

    by_pair = defaultdict(list)
    for row in rows:
        by_pair[(row["player_strategy"], row["dealer_strategy"])].append(row)

    for pair, pair_rows in by_pair.items():
        if len(pair_rows) < BATCH_SIZE:
            log(
                AGENT_NAME,
                f"{pair[0]} vs {pair[1]}: {len(pair_rows)} new rounds "
                f"(< {BATCH_SIZE}), deferring analysis to next batch.",
            )
            continue
        _analyze_batch(pair, pair_rows, a_state)

    save_state(state)


def _analyze_batch(pair, rows, a_state):
    n = len(rows)
    bust = sum(1 for r in rows if r["player_value"] > 21) / n
    win = sum(1 for r in rows if r["winner"] == "player") / n
    loss = sum(1 for r in rows if r["winner"] == "dealer") / n
    push = sum(1 for r in rows if r["winner"] == "push") / n
    label = f"{pair[0]} vs {pair[1]}"

    breaches = []
    if bust > BUST_CEILING:
        breaches.append(f"player bust rate {bust:.1%} exceeds ceiling {BUST_CEILING:.0%}")
    if not (WIN_RATE_RANGE[0] <= win <= WIN_RATE_RANGE[1]):
        breaches.append(
            f"player win rate {win:.1%} outside expected range "
            f"{WIN_RATE_RANGE[0]:.0%}-{WIN_RATE_RANGE[1]:.0%}"
        )

    if not breaches:
        log(
            AGENT_NAME,
            f"{label}: n={n} win={win:.1%} loss={loss:.1%} push={push:.1%} bust={bust:.1%} "
            "-- within normal range.",
        )
        return

    key = "|".join(pair)
    last = a_state["last_reported"].get(key, 0)
    if time.time() - last < COOLDOWN_SECONDS:
        log(
            AGENT_NAME,
            f"{label}: anomaly persists ({'; '.join(breaches)}) -- already reported "
            "recently, skipping duplicate report.",
        )
        return

    log(AGENT_NAME, f"ANOMALY {label}: {'; '.join(breaches)} (n={n})")
    report = _investigate(label, n, win, loss, push, bust, breaches)
    path = _write_report(label, report)
    committed = git_commit([path], f"chore: anomaly report for {label}", *AUTHOR)
    if committed:
        log(AGENT_NAME, f"filed incident report {path.relative_to(REPO_ROOT)} and committed.")
    a_state["last_reported"][key] = time.time()


def _investigate(label, n, win, loss, push, bust, breaches) -> IncidentReport:
    sources = {
        name: (REPO_ROOT / "casino" / f"{name}.py").read_text()
        for name in ("table", "strategies", "hand")
    }
    agent = Agent(model=make_model(max_tokens=1500), callback_handler=None)
    result = agent(
        f"A blackjack table monitor flagged an anomaly for strategy pairing {label} over "
        f"the last {n} rounds: win={win:.1%} loss={loss:.1%} push={push:.1%} bust={bust:.1%}. "
        f"Breached thresholds: {'; '.join(breaches)}.\n\nRelevant source:\n\n"
        + "\n\n".join(f"casino/{name}.py:\n```python\n{src}\n```" for name, src in sources.items())
        + "\n\nProduce an incident report.",
        structured_output_model=IncidentReport,
    )
    return result.structured_output


def _write_report(label, report: IncidentReport) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = REPORTS_DIR / f"anomaly_{ts}.md"
    path.write_text(
        f"# {report.title}\n\n"
        f"- **Pairing:** {label}\n"
        f"- **Severity:** {report.severity}\n"
        f"- **Detected:** {ts}\n\n"
        f"## Evidence\n{report.evidence}\n\n"
        f"## Likely cause\n{report.likely_cause}\n\n"
        f"## Recommendation\n{report.recommendation}\n"
    )
    return path
