# Casino Skeleton

Blackjack simulator. Run `python -m casino.simulate`.

## Architecture

The simulator lives under `casino/` as small, single-purpose modules. `cards.py` defines
`Card` and `Deck` (a shuffled, N-deck stack with `draw()`). `hand.py` defines `Hand`, which
accumulates `Card`s and knows its own blackjack value (soft-ace reduction), bust state, and
whether it's a natural blackjack. `shoe.py` defines `Shoe`, a persistent multi-round wrapper
around `Deck`: rather than rebuilding a fresh deck every round, it draws from one live deck
across many hands and reshuffles itself automatically once a configurable cut-card
penetration threshold is crossed. `strategies.py` defines the decision logic as small
interchangeable classes: `PlayerStrategy`/`DealerStrategy` base classes with a
`should_hit(hand, ...)` method, and concrete strategies (`BasicPlayerStrategy` stands at
17, `AggressivePlayerStrategy` stands at 20 as a deliberately-suboptimal fixture,
`StandardDealerStrategy` hits to 17) identified by a `name` used in logging.

`table.py` holds the core `Table` class, constructed with a player strategy, a dealer
strategy, and a deck count. `Table.play_round()` deals two cards each from a fresh `Deck`,
lets the player hit per their strategy until they stand or bust, then does the same for the
dealer, and resolves the winner by comparing hand values (or bust) into an outcome dict.
`payouts.py` defines `Bankroll`, the money layer: it holds a chip balance, deducts bets via
`place_bet()`, and turns a round's outcome string (plus a caller-supplied blackjack flag)
into winnings via `resolve()`, applying the standard 3:2 blackjack bonus -- it stays
decoupled from `Table`, reasoning only about the outcome string so it can be dropped in
without touching round-playing code. `monitor.py` provides `Monitor`, a thin JSON-lines
appender that persists each outcome to `outcomes.jsonl`. `simulate.py` wires the core loop
together: it builds a `Table` with concrete strategies, loops `play_round()` for
`num_rounds`, and records each outcome via `Monitor`, so a round flows Deck/Hand setup ->
player strategy loop -> dealer strategy loop -> outcome dict -> `outcomes.jsonl`, with
`Shoe` and `Bankroll` available as drop-in building blocks for persistent-shoe dealing and
real-money accounting on top of that same flow.

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

**Observability:** `agents/common.py` calls `mlflow.strands.autolog()` on import, so every
Strands `Agent` call from any of the three agents -- prompts, completions, tool calls,
latency, token usage, cost -- is traced automatically with no code changes inside the
agents themselves. Separately, the Anomaly Detection Agent logs the casino's own outcome
stats (win/loss/push/bust rate per strategy pairing, plus a 0/1 breach flag) as MLflow
metrics on every batch, not just on a breach, so the same drift the agent reacts to is
visible as a plotted trend rather than only as one-off incident reports. Everything writes
to a local SQLite store (`mlflow.db`, gitignored); view it with:

```
mlflow ui --backend-store-uri sqlite:///mlflow.db
```

then open the `casino-agent-layer` experiment. `python3 -m agents.dashboard` (http://127.0.0.1:8765)
gives a lighter-weight live view of the same underlying data -- a stdlib-only web page that
polls `agents/activity.log`, parsed into color-coded, per-agent events with running
summary counts. It only reads the log, so it's safe to run at any time regardless of
whether the orchestrator is up. It's deliberately minimal (poll a JSON endpoint) so it's an
easy base to grow into a real UI later -- push instead of poll, an MLflow trace/metric panel
alongside the log -- without changing where the data comes from.

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
which would adapt as legitimate new strategies are added -- I saw this cost it a false
positive live, flagging ordinary sampling variance on the standard strategy pairing at
n=50. `enforce_scope` also isn't safe against concurrent writers: it reverts any tracked
file it doesn't recognize as in-scope, which means a human hand-editing a tracked file
while the orchestrator is running gets silently reverted too (this happened to me once
while iterating on this same layer). The fix in both directions is the same -- don't edit
tracked files while the orchestrator has an in-flight tick -- but a proper lock file would
make that safe instead of just documented. And there's no dependency-update agent --
`requirements.txt` still pins `requests==2.6.0`, which is unused dead weight from the
starter repo, worth flagging or removing if this were in scope.
