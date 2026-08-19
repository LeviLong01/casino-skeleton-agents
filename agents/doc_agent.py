"""Documentation Agent.

Trigger: an AST-level "architecture snapshot" of casino/*.py (modules,
classes + base classes, top-level function signatures) is diffed against the
snapshot this agent saw last time. If nothing changed, there's nothing to do
-- no LLM call.

If something changed, one LLM call judges whether the change is
*structurally* significant (new module, new class/abstraction, changed core
control flow, new external dependency) as opposed to a trivial internal edit
(new method on an existing class, a rename, a docstring tweak). This is
deliberately not a changelog: cosmetic diffs are ignored, and when it does
rewrite the README, it regenerates the Architecture section from the CURRENT
code -- not from the diff -- so the doc never accumulates change-log cruft.
"""
from pydantic import BaseModel, Field
from strands import Agent
from strands_tools import editor, file_read, file_write

from agents.common import (
    REPO_ROOT,
    activity_callback,
    architecture_snapshot,
    enforce_scope,
    git_commit,
    load_state,
    log,
    make_model,
    save_state,
)

AGENT_NAME = "DocumentationAgent"
AUTHOR = ("Documentation Agent", "agent-docs@casino.local")
README_PATH = REPO_ROOT / "README.md"
SECTION_HEADER = "## Architecture"


class SignificanceVerdict(BaseModel):
    """Whether a code change is architecturally significant enough to
    warrant a README rewrite."""

    significant: bool = Field(
        description=(
            "True only for structural change: a new module, a new class or major "
            "abstraction, a changed core control flow, or a new external "
            "dependency/integration. False for renames, docstring/formatting edits, "
            "or a new method added to an existing class of the same overall shape."
        )
    )
    reasoning: str = Field(description="One or two sentences justifying the verdict.")


def diff_summary(old: dict, new: dict) -> str:
    lines = []
    for module in sorted(set(old) | set(new)):
        old_syms = {s["name"] for s in old.get(module, [])}
        new_syms = {s["name"] for s in new.get(module, [])}
        if module not in old:
            lines.append(f"+ new module casino/{module}.py: {sorted(new_syms)}")
        elif module not in new:
            lines.append(f"- removed module casino/{module}.py")
        else:
            added, removed = new_syms - old_syms, old_syms - new_syms
            if added:
                lines.append(f"~ casino/{module}.py: added {sorted(added)}")
            if removed:
                lines.append(f"~ casino/{module}.py: removed {sorted(removed)}")
    return "\n".join(lines) if lines else "(no symbol-level changes)"


def tick():
    state = load_state()
    doc_state = state.setdefault("doc_agent", {})
    new_snapshot = architecture_snapshot()
    old_snapshot = doc_state.get("last_snapshot")
    has_section = SECTION_HEADER in README_PATH.read_text()

    if old_snapshot is not None and old_snapshot == new_snapshot and has_section:
        log(AGENT_NAME, "architecture scan: no structural change since last check. No action.")
        return

    if old_snapshot is None or not has_section:
        log(AGENT_NAME, "architecture scan: README has no Architecture section yet -- bootstrapping it.")
        significant, reasoning = True, "bootstrap: README has no Architecture section yet"
    else:
        summary = diff_summary(old_snapshot, new_snapshot)
        log(AGENT_NAME, f"architecture scan: symbol-level diff since last check:\n{summary}")
        verdict = _judge_significance(summary)
        significant, reasoning = verdict.significant, verdict.reasoning
        log(AGENT_NAME, f"significance verdict: significant={significant} -- {reasoning}")

    if significant:
        _update_readme(reasoning)

    doc_state["last_snapshot"] = new_snapshot
    save_state(state)


def _judge_significance(summary: str) -> SignificanceVerdict:
    agent = Agent(model=make_model(max_tokens=512), callback_handler=None)
    result = agent(
        "Here is a symbol-level diff of a small Python blackjack simulator's "
        "public classes/functions since the README was last reviewed:\n\n"
        f"{summary}\n\n"
        "Judge whether this warrants rewriting the README's architecture description.",
        structured_output_model=SignificanceVerdict,
    )
    return result.structured_output


def _update_readme(reasoning: str):
    agent = Agent(
        model=make_model(max_tokens=4096),
        system_prompt=(
            "You maintain the README of a small Python blackjack simulator. Working "
            "directory is the repository root; use paths relative to it. You only ever "
            f"touch the '{SECTION_HEADER}' section of README.md -- everything before and "
            "after it must be left exactly as it is. Read the current casino/*.py sources "
            "with file_read, then use editor/file_write to replace the Architecture section "
            "with an accurate, concise (150-300 word) description of the modules, the core "
            "classes, and how a round flows through them. This is a living description of "
            "the current design, not a changelog -- never mention diffs, dates, or what "
            "changed."
        ),
        tools=[file_read, file_write, editor],
        callback_handler=activity_callback(AGENT_NAME),
    )
    agent(
        f"Update the '{SECTION_HEADER}' section of README.md to reflect the current code "
        f"in casino/. Reason this update was triggered: {reasoning}. If the section doesn't "
        "exist yet, add it near the top of the README, right after the introductory "
        "paragraph."
    )

    enforce_scope({README_PATH}, AGENT_NAME)

    if SECTION_HEADER not in README_PATH.read_text():
        log(AGENT_NAME, "post-check failed: Architecture section missing after edit; leaving for manual review.")
        return

    committed = git_commit(
        [README_PATH], "docs: refresh Architecture section to match current code", *AUTHOR
    )
    if committed:
        log(AGENT_NAME, "committed README Architecture update.")
    else:
        log(AGENT_NAME, "model ran but README content is unchanged; nothing to commit.")
