# Casino Skeleton — Agent Layer Submission

**Running it:** set `ANTHROPIC_API_KEY` (a `.env` file in the repo root works), `pip install -r
requirements.txt`, then run `python3 -m agents.orchestrator` and leave it running — it polls
every 15s, simulates a batch of casino traffic, and gives each agent a chance to check its own
trigger and act if warranted. `python3 -m agents.dashboard` (http://127.0.0.1:8765) gives a live
view of what's happening. Full details — including MLflow observability and trace evaluation —
are in `README.md`.

**The three agents**, all built on the Strands Agents SDK calling Claude Sonnet 5, each fire on
their own initiative: the **Test Writer Agent** triggers on a new commit that leaves a public
`casino/` symbol untested (an AST scan against `tests/`), writes and independently verifies
pytest tests, and commits only if the suite is green. The **Documentation Agent** triggers on
structural drift — an AST snapshot diff across two scopes, the casino simulator and the agent
layer's own code — judged by an LLM for whether it's *significant* before regenerating the
relevant README section from current source (never a changelog). The **Anomaly Detection
Agent** triggers on new simulated rounds landing in `outcomes.jsonl`, checks bust/win rates
against calibrated bounds per strategy pairing, and on a breach has an LLM read the actual
source and file a structured incident report.

**AI tools used:** Claude Code (Sonnet 5) built this entire agent layer interactively — every
file under `agents/`, the deliberately-flawed `AggressivePlayerStrategy` fixture used to give
the anomaly agent real signal, and both READMEs — with me directing scope and reviewing every
change. The three *deployed* agents are separate from that: each is its own Strands `Agent`
instance calling Claude autonomously, with no per-action approval once the orchestrator is
running.

**What didn't go as planned / what I'd improve:** a real git `post-commit` hook for the Test
Writer Agent worked for a single invocation but mysteriously double-logged every action (same
PID both times — never fully diagnosed), so it reverted to polling with a commit-sha gate
instead, which is logically still "triggered by a commit," just checked on a timer rather than
fired by the hook. The `enforce_scope` safety guard — which reverts any file an agent touches
outside what it owns before committing — doesn't distinguish an agent's stray edit from a
human's uncommitted work-in-progress; it reverted my own uncommitted changes twice mid-session
before I adopted the discipline of always committing before running any agent code. With more
time I'd replace the test-writer's coverage check (a word-boundary text match, not real
coverage instrumentation) with `coverage.py`, and make the anomaly agent's thresholds a rolling
per-pairing statistical baseline instead of fixed bounds — the fixed bounds produced a handful
of real false positives on ordinary sampling variance at a 50-round batch size.
