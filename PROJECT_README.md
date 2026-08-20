# Casino Skeleton — Agent Layer Submission

**Running it:** Set `ANTHROPIC_API_KEY` (a `.env` file works), `pip install -r
requirements.txt`, then run `python3 -m agents.orchestrator` and leave it running. Live
dashboard: `python3 -m agents.dashboard` → http://127.0.0.1:8765. Full details in `README.md`.

**Agents & triggers:**
- **Test Writer** — fires on a commit that leaves a `casino/` symbol untested; writes and
  verifies pytest tests, commits only if green.
- **Documentation** — fires on structural code drift (casino simulator or the agent layer
  itself); regenerates the relevant README section from current source.
- **Anomaly Detection** — fires on new simulated rounds; flags bust/win rates outside
  calibrated bounds and files an incident report.

**AI tools:** Claude Code (Sonnet 5) built this entire agent layer interactively, with me
directing scope and reviewing every change. The three deployed agents are separate: each is
its own Strands `Agent` calling Claude Sonnet 5 autonomously, no per-action approval.

**What Claude would want to improve:** A real git hook for the Test Writer worked but mysteriously double-logged
every action (unexplained) — reverted to polling instead. The `enforce_scope` safety guard
reverted my own uncommitted edits twice, since it can't tell an agent's stray change from a
human's work-in-progress. Anomaly thresholds are fixed, not an adaptive baseline, so it
produced a few false positives on normal sampling variance. Test coverage check is a text
heuristic, not real coverage instrumentation.

**What I (Levi) would want to improve**: 