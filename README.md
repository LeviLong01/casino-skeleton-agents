# Casino Skeleton

Blackjack simulator. Run `python -m casino.simulate`.

## Running the Simulator

```
pip install -r requirements.txt
python3 -m pytest tests/ -q
python3 -m casino.simulate
```

## Autonomous Agent Layer

Three agents built on the [Strands Agents](https://strandsagents.com) SDK maintain this
repo on their own initiative, each with its own deterministic trigger (checked in code,
not by prompting an LLM every tick) and its own git identity so their commits are
distinguishable in history. All three are wired together by `agents/orchestrator.py`,
which also runs a small traffic generator (simulates batches of rounds into
`outcomes.jsonl`, occasionally through a deliberately over-aggressive strategy) so the
layer has something to react to without a human driving it.

- **Test Writer Agent** (`agents/test_writer_agent.py`) -- triggers on a coverage gap: an
  AST scan of `casino/*.py` finds a public class/function never referenced by name in
  `tests/`. It hands the gap to a tool-using Strands agent that writes pytest tests and
  runs the suite itself; the orchestrator independently re-runs pytest before trusting the
  result and commits only on green.
- **Documentation Agent** (`agents/doc_agent.py`) -- triggers on architectural drift: an AST
  snapshot of modules/classes/signatures is diffed on every tick, and an LLM call judges
  whether the diff is *structurally* significant (new module, new abstraction, new
  integration) versus a trivial internal edit. On a significant change it regenerates the
  `## Architecture` section below from the current code (not a changelog of the diff) and
  commits.
- **Anomaly Detection Agent** (`agents/anomaly_agent.py`) -- triggers on new rows landing in
  `outcomes.jsonl`: per strategy pairing, it checks player bust/win rate against bounds
  calibrated from a real 3000-round baseline run. A breach triggers an LLM call that reads
  the actual `table.py`/`strategies.py`/`hand.py` source, hypothesizes a root cause, and
  files a structured incident report under `agents/reports/`, committed.

Each agent is a deterministic trigger (cheap, no LLM cost while idle) wired to an
LLM-driven action; the LLM's tool use is deliberately scoped -- git commits are never
delegated to a tool call, and an `enforce_scope` guard reverts any file an agent touches
outside what it owns before anything is committed. Every tick, whether or not an agent
acts, is logged to `agents/activity.log` and the console.

**To run it:** `ANTHROPIC_API_KEY` must be set (`.env` in the repo root works), then:

```
pip install -r requirements.txt
python3 -m agents.orchestrator
```

Leave it running -- it polls every `AGENT_TICK_SECONDS` (default 15s) and acts only when a
trigger actually fires. `agents/state/state.json` (gitignored) tracks each agent's
last-seen fingerprint/offset across restarts.

**AI tools used:** Claude Code (Sonnet 5) was used interactively to design and write this
agent layer itself -- every file under `agents/`, the `AggressivePlayerStrategy` fixture,
and this README section. The three deployed agents are separate: each is its own Strands
`Agent` calling the Claude Sonnet 5 API (`claude-sonnet-5`) autonomously, with no human
approving individual actions once the orchestrator is running.

**What I'd improve with more time:** the test-writer's coverage check is a name-in-source
heuristic (word-boundary match), not real coverage instrumentation, so it can be fooled by
a symbol name that merely appears in an unrelated test; swapping in `coverage.py` would be
more precise. The anomaly agent's thresholds are fixed bounds from one calibration run
rather than a rolling statistical baseline (e.g. Welford's algorithm per strategy pair),
which would adapt as legitimate new strategies are added. And there's no dependency-update
agent -- `requirements.txt` still pins `requests==2.6.0`, which is unused dead weight from
the starter repo, worth flagging or removing if this were in scope.
