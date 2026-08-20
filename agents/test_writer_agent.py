"""Test Writer Agent.

Trigger: the repo's HEAD commit, checked on the orchestrator's poll (not on
a fixed schedule of its own): tick() compares `git rev-parse HEAD` against
the last commit it checked and does nothing -- no scan, no log line -- if
nothing has been committed since, by a human or either other agent. Only
when HEAD has moved does it run the actual check: an AST scan of casino/*.py
for a public class/function whose name never appears, as a whole word,
anywhere under tests/. That scan is deterministic and free -- no LLM call is
spent just to detect a gap. When a gap spans multiple modules, only one is
handled per tick; its own successful commit changes HEAD again, so the next
poll picks up the rest.

(A real git post-commit hook was tried here instead of polling -- it worked,
but a still-unexplained bug made hook-triggered invocations log every action
twice, always with the *same* PID, which rules out a simple double-spawn.
Not worth chasing further right now, so this reverted to polling; the
commit-sha gate above is what keeps polling cheap and quiet when idle.)

Action: a Strands agent with file_read/file_write/editor/shell tools is
handed the gap and the module's source and asked to write pytest tests for
the missing symbols, running pytest itself until the suite is green. We
still independently re-run pytest ourselves before trusting the result, and
the model's shell tool is never allowed to touch git -- commits are made
here, deterministically, only after our own verification passes.
"""
import re

from strands import Agent
from strands_tools import editor, file_read, file_write, shell

from agents.common import (
    REPO_ROOT,
    activity_callback,
    casino_modules,
    enforce_scope,
    git_commit,
    git_head_sha,
    load_state,
    log,
    make_model,
    public_symbols,
    run_pytest,
    save_state,
)

AGENT_NAME = "TestWriterAgent"
AUTHOR = ("Test Writer Agent", "agent-test-writer@casino.local")
MAX_ATTEMPTS = 2

SYSTEM_PROMPT = """You are a meticulous Python test engineer working on a small
blackjack simulator (the `casino` package). You write pytest tests only -- you
never modify files under casino/. Working directory is the repository root;
use paths relative to it.

Given a module's source and a list of its public classes/functions that
currently have no test coverage, write clear, fast, deterministic pytest
tests for them in the given test file path (create it if it doesn't exist,
append to it if it does -- never delete or rewrite existing tests in that
file). Card draws are random; where determinism matters, construct
Card/Hand objects directly rather than relying on a shuffled Deck.

After writing the tests, run `python3 -m pytest tests/ -q` with the shell
tool and iterate until the full suite passes. Do not run any git commands.
Stop once the suite is green."""


def find_gaps():
    test_dir = REPO_ROOT / "tests"
    test_source = "\n".join(p.read_text() for p in test_dir.glob("test_*.py"))
    gaps = {}
    for module_path in casino_modules():
        missing = [
            s["name"]
            for s in public_symbols(module_path)
            if not re.search(rf"\b{re.escape(s['name'])}\b", test_source)
        ]
        if missing:
            gaps[module_path.stem] = missing
    return gaps


def tick():
    state = load_state()
    tw_state = state.setdefault("test_writer", {"attempts": {}, "last_checked_sha": None})
    current_sha = git_head_sha()

    if current_sha == tw_state.get("last_checked_sha"):
        return  # no new commit since we last looked; nothing to check

    gaps = find_gaps()

    if not gaps:
        log(
            AGENT_NAME,
            f"commit {current_sha[:7]}: every public symbol in casino/ is referenced by a test. No action.",
        )
        tw_state["last_checked_sha"] = current_sha
        save_state(state)
        return

    for module_name, missing in gaps.items():
        if tw_state["attempts"].get(module_name, 0) >= MAX_ATTEMPTS:
            continue
        _handle_gap(module_name, missing, tw_state)
        save_state(state)
        return  # one gap per tick keeps a live run easy to follow; the
        # commit this makes on success naturally re-triggers next tick

    log(
        AGENT_NAME,
        f"commit {current_sha[:7]}: gaps remain in {sorted(gaps)} but max attempts reached for each; "
        "skipping until the next commit.",
    )
    tw_state["last_checked_sha"] = current_sha
    save_state(state)


def _handle_gap(module_name, missing, tw_state):
    module_path = REPO_ROOT / "casino" / f"{module_name}.py"
    test_path = REPO_ROOT / "tests" / f"test_{module_name}.py"
    rel_test_path = test_path.relative_to(REPO_ROOT)
    original = test_path.read_text() if test_path.exists() else None

    log(
        AGENT_NAME,
        f"coverage gap: casino/{module_name}.py missing tests for {missing} -> writing {rel_test_path}",
    )

    agent = Agent(
        model=make_model(max_tokens=4096),
        system_prompt=SYSTEM_PROMPT,
        tools=[file_read, file_write, editor, shell],
        callback_handler=activity_callback(AGENT_NAME),
    )
    agent(
        f"Module: casino/{module_name}.py\n\n"
        f"Source:\n```python\n{module_path.read_text()}\n```\n\n"
        f"Untested public symbols: {missing}\n"
        f"Test file to create/extend: {rel_test_path}"
    )

    tw_state["attempts"][module_name] = tw_state["attempts"].get(module_name, 0) + 1

    enforce_scope({test_path}, AGENT_NAME)

    ok, output = run_pytest()
    if not ok:
        log(
            AGENT_NAME,
            f"verification failed after writing tests for {module_name}; reverting the attempt.\n"
            f"{output[-1200:]}",
        )
        if original is None:
            test_path.unlink(missing_ok=True)
        else:
            test_path.write_text(original)
        return

    committed = git_commit(
        [test_path],
        f"test: add coverage for casino/{module_name}.py ({', '.join(missing)})",
        *AUTHOR,
    )
    if committed:
        log(AGENT_NAME, f"pytest green; committed new tests for {module_name}.")
        tw_state["attempts"][module_name] = 0
    else:
        log(AGENT_NAME, f"pytest green but nothing new staged for {module_name} (model made no changes).")


if __name__ == "__main__":
    tick()
