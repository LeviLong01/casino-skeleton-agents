"""Documentation Agent.

Trigger: an AST-level "architecture snapshot" is diffed against the snapshot
this agent saw last time, on two independent scopes:
  - casino/*.py (the game itself)          -> the '## Architecture' section
  - agents/*.py (the agent layer's own code) -> the '## Agent Layer Modules'
    section
Each scope is checked and, if warranted, updated independently -- a change
in one doesn't trigger a rewrite of the other's section, and each has its
own last-seen snapshot in state. If nothing changed in a given scope,
there's nothing to do for it -- no LLM call.

(The agents/ scope exists because the Test Writer Agent's coverage scan is
deliberately restricted to casino/ -- the agent layer doesn't test itself --
which meant new modules like agents/evaluate.py and agents/dashboard.py had
no autonomous documentation path at all; the "Autonomous Agent Layer"
section of the README was entirely hand-written. This gives the agent layer
its own architecture scope, so additions to it get picked up the same way
casino/ additions do.)

If something changed in a scope, one LLM call judges whether the change is
*structurally* significant (new module, new class/abstraction, changed core
control flow, new external dependency) as opposed to a trivial internal edit
(new method on an existing class, a rename, a docstring tweak). This is
deliberately not a changelog: cosmetic diffs are ignored, and when it does
rewrite a section, it regenerates that section from the CURRENT code -- not
from the diff -- so the doc never accumulates change-log cruft.
"""
from dataclasses import dataclass
from typing import Callable

from pydantic import BaseModel, Field
from strands import Agent
from strands_tools import editor, file_read, file_write

from agents.common import (
    REPO_ROOT,
    activity_callback,
    agent_layer_snapshot,
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


@dataclass
class Scope:
    state_key: str
    snapshot_fn: Callable[[], dict]
    section_header: str
    path_prefix: str  # used only to label the diff summary, e.g. "casino" or "agents"
    subject: str  # what this section should describe, for the update agent's prompt
    insert_instruction: str
    commit_message: str


SCOPES = [
    Scope(
        state_key="last_snapshot",
        snapshot_fn=architecture_snapshot,
        section_header="## Architecture",
        path_prefix="casino",
        subject=(
            "the casino/ blackjack simulator: the modules, the core classes, and how a "
            "round flows through them"
        ),
        insert_instruction="add it near the top of the README, right after the introductory paragraph",
        commit_message="docs: refresh Architecture section to match current code",
    ),
    Scope(
        state_key="agent_layer_last_snapshot",
        snapshot_fn=agent_layer_snapshot,
        section_header="## Agent Layer Modules",
        path_prefix="agents",
        subject=(
            "the agents/ package itself -- what each module in the autonomous agent layer "
            "is responsible for (the orchestrator, each of the three agents, the shared "
            "helpers in common.py, the activity dashboard, the evaluation script). This is "
            "a module reference, distinct from the prose already in the "
            "'## Autonomous Agent Layer' section above it -- don't duplicate that, just say "
            "what each module contains"
        ),
        insert_instruction="add it as a new section at the very end of the README",
        commit_message="docs: refresh Agent Layer Modules section to match current code",
    ),
]


def diff_summary(old: dict, new: dict, path_prefix: str) -> str:
    lines = []
    for module in sorted(set(old) | set(new)):
        old_syms = {s["name"] for s in old.get(module, [])}
        new_syms = {s["name"] for s in new.get(module, [])}
        if module not in old:
            lines.append(f"+ new module {path_prefix}/{module}.py: {sorted(new_syms)}")
        elif module not in new:
            lines.append(f"- removed module {path_prefix}/{module}.py")
        else:
            added, removed = new_syms - old_syms, old_syms - new_syms
            if added:
                lines.append(f"~ {path_prefix}/{module}.py: added {sorted(added)}")
            if removed:
                lines.append(f"~ {path_prefix}/{module}.py: removed {sorted(removed)}")
    return "\n".join(lines) if lines else "(no symbol-level changes)"


def tick():
    state = load_state()
    doc_state = state.setdefault("doc_agent", {})
    for scope in SCOPES:
        _check_scope(doc_state, scope)
        save_state(state)


def _check_scope(doc_state: dict, scope: Scope):
    new_snapshot = scope.snapshot_fn()
    old_snapshot = doc_state.get(scope.state_key)
    has_section = scope.section_header in README_PATH.read_text()

    if old_snapshot is not None and old_snapshot == new_snapshot and has_section:
        log(AGENT_NAME, f"'{scope.section_header}': no structural change since last check. No action.")
        return

    if old_snapshot is None or not has_section:
        log(AGENT_NAME, f"'{scope.section_header}': README section missing -- bootstrapping it.")
        significant, reasoning = True, f"bootstrap: README has no '{scope.section_header}' section yet"
    else:
        summary = diff_summary(old_snapshot, new_snapshot, scope.path_prefix)
        log(AGENT_NAME, f"'{scope.section_header}': symbol-level diff since last check:\n{summary}")
        verdict = _judge_significance(summary)
        significant, reasoning = verdict.significant, verdict.reasoning
        log(
            AGENT_NAME,
            f"'{scope.section_header}' significance verdict: significant={significant} -- {reasoning}",
        )

    if significant:
        _update_readme(scope, reasoning)

    doc_state[scope.state_key] = new_snapshot


def _judge_significance(summary: str) -> SignificanceVerdict:
    agent = Agent(model=make_model(max_tokens=512), callback_handler=None)
    result = agent(
        "Here is a symbol-level diff of a small Python project's public classes/functions "
        "since a README section was last reviewed:\n\n"
        f"{summary}\n\n"
        "Judge whether this warrants rewriting that section.",
        structured_output_model=SignificanceVerdict,
    )
    return result.structured_output


def _update_readme(scope: Scope, reasoning: str):
    agent = Agent(
        model=make_model(max_tokens=4096),
        system_prompt=(
            "You maintain the README of a small Python project. Working directory is the "
            "repository root; use paths relative to it. You only ever touch the "
            f"'{scope.section_header}' section of README.md -- everything before and after "
            "it must be left exactly as it is. Read the current source with file_read, then "
            "use editor/file_write to replace that section with an accurate, concise "
            f"(150-300 word) description of {scope.subject}. This is a living description "
            "of the current design, not a changelog -- never mention diffs, dates, or what "
            "changed."
        ),
        tools=[file_read, file_write, editor],
        callback_handler=activity_callback(AGENT_NAME),
    )
    agent(
        f"Update the '{scope.section_header}' section of README.md to reflect the current "
        f"code. Reason this update was triggered: {reasoning}. If the section doesn't exist "
        f"yet, {scope.insert_instruction}."
    )

    enforce_scope({README_PATH}, AGENT_NAME)

    if scope.section_header not in README_PATH.read_text():
        log(
            AGENT_NAME,
            f"post-check failed: '{scope.section_header}' missing after edit; leaving for manual review.",
        )
        return

    committed = git_commit([README_PATH], scope.commit_message, *AUTHOR)
    if committed:
        log(AGENT_NAME, f"committed README update for '{scope.section_header}'.")
    else:
        log(
            AGENT_NAME,
            f"model ran but README content is unchanged for '{scope.section_header}'; nothing to commit.",
        )
