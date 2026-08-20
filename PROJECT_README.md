# Casino Skeleton — Agent Layer Submission

Set `ANTHROPIC_API_KEY` (a `.env` file in the repo root works), `pip install -r
requirements.txt`, then run `python3 -m agents.orchestrator` and leave it running — it polls
every 15s, simulates a batch of casino traffic, and lets each agent check its own trigger and
act if warranted (`python3 -m agents.dashboard`, at http://127.0.0.1:8765, gives a live view;
full details including MLflow observability and evaluation are in `README.md`). Three agents,
all Strands Agents SDK instances calling Claude Sonnet 5, act on their own initiative: the
**Test Writer Agent** triggers on a commit that leaves a public `casino/` symbol untested (an
AST scan against `tests/`), writes and independently verifies pytest tests, and commits only if
the suite is green; the **Documentation Agent** triggers on structural drift in either the
casino simulator or the agent layer's own code (an AST snapshot diff, judged by an LLM for
significance) and regenerates the relevant README section from current source, never a
changelog; the **Anomaly Detection Agent** triggers on new simulated rounds landing in
`outcomes.jsonl`, checks bust/win rates against calibrated bounds per strategy pairing, and on a
breach has an LLM read the actual source and file a structured incident report.

Claude Code (Sonnet 5) built this entire agent layer interactively — every file under `agents/`,
the deliberately-flawed `AggressivePlayerStrategy` fixture used to give the anomaly agent real
signal, and both READMEs — with me directing scope and reviewing every change; the three
*deployed* agents are separate from that, each its own Strands `Agent` instance calling Claude
autonomously with no per-action approval once the orchestrator is running. A real git
`post-commit` hook for the Test Writer Agent worked for a single invocation but mysteriously
double-logged every action (same PID both times, never fully diagnosed), so it reverted to
polling with a commit-sha gate instead — still logically "triggered by a commit," just checked
on a timer. The `enforce_scope` safety guard, which reverts any file an agent touches outside
what it owns before committing, doesn't distinguish an agent's stray edit from a human's
uncommitted work-in-progress; it reverted my own uncommitted changes twice mid-session before I
adopted the discipline of always committing before running agent code. With more time I'd
replace the test-writer's coverage check (a word-boundary text match, not real coverage
instrumentation) with `coverage.py`, and make the anomaly thresholds a rolling per-pairing
statistical baseline instead of fixed bounds, which produced a handful of real false positives
on ordinary sampling variance at a 50-round batch size.
