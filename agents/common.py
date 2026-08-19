"""Shared infrastructure for the autonomous agent layer: state persistence,
scoped git commits, activity logging, and lightweight AST introspection of
the casino package that the test-writer and documentation agents both need.
"""
import ast
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = REPO_ROOT / "agents" / "state"
STATE_PATH = STATE_DIR / "state.json"
ACTIVITY_LOG = REPO_ROOT / "agents" / "activity.log"

MODEL_ID = "claude-sonnet-5"


def _load_env():
    """Minimal .env loader so ANTHROPIC_API_KEY is available without adding
    a python-dotenv dependency for one line of parsing."""
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env()
# Tool-using Strands agents run unattended here; without these, file_write /
# editor / shell would block on an interactive consent prompt that nobody is
# there to answer.
os.environ.setdefault("BYPASS_TOOL_CONSENT", "true")
os.environ.setdefault("STRANDS_NON_INTERACTIVE", "true")


def log(agent: str, message: str):
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"[{timestamp}] [{agent}] {message}"
    print(line, flush=True)
    ACTIVITY_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(ACTIVITY_LOG, "a") as f:
        f.write(line + "\n")


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {}


def save_state(state: dict):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True))


def git_commit(paths, message: str, author_name: str, author_email: str) -> bool:
    """Stage exactly the given paths and commit under a distinct agent
    identity. Returns False (no-op) if there was nothing to commit."""
    subprocess.run(["git", "add", *[str(p) for p in paths]], cwd=REPO_ROOT, check=True)
    staged = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=REPO_ROOT)
    if staged.returncode == 0:
        return False
    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": author_name,
            "GIT_AUTHOR_EMAIL": author_email,
            "GIT_COMMITTER_NAME": author_name,
            "GIT_COMMITTER_EMAIL": author_email,
        }
    )
    subprocess.run(["git", "commit", "-m", message], cwd=REPO_ROOT, check=True, env=env)
    return True


def enforce_scope(allowed_paths, agent_name: str):
    """Revert or delete any working-tree change outside `allowed_paths`.

    Tool-using agents get broad file_write/editor access so they can read
    around the repo, but each agent is only supposed to *change* the files
    it owns (a test file, README.md, ...). This is the deterministic
    backstop for that boundary -- it runs after every agentic call, before
    anything gets committed.
    """
    allowed = {Path(p).resolve() for p in allowed_paths}
    result = subprocess.run(
        ["git", "status", "--porcelain"], cwd=REPO_ROOT, capture_output=True, text=True
    )
    violations = []
    for line in result.stdout.splitlines():
        status, rel_path = line[:2], line[3:].strip()
        full = (REPO_ROOT / rel_path).resolve()
        if full in allowed:
            continue
        violations.append(rel_path)
        if status.strip() == "??":
            if full.is_dir():
                shutil.rmtree(full, ignore_errors=True)
            else:
                full.unlink(missing_ok=True)
        else:
            subprocess.run(["git", "checkout", "--", rel_path], cwd=REPO_ROOT)
    if violations:
        log(agent_name, f"scope guard: reverted out-of-scope changes to {violations}")


def run_pytest():
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0, (result.stdout + result.stderr)


# ---- AST introspection over casino/, shared by the test-writer and doc agents ----


def casino_modules():
    casino_dir = REPO_ROOT / "casino"
    return sorted(p for p in casino_dir.glob("*.py") if p.name != "__init__.py")


def public_symbols(path: Path):
    """Top-level public class/function definitions with a light signature."""
    tree = ast.parse(path.read_text())
    symbols = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            bases = [ast.unparse(b) for b in node.bases]
            methods = sorted(
                n.name
                for n in node.body
                if isinstance(n, ast.FunctionDef) and not n.name.startswith("_")
            )
            symbols.append({"type": "class", "name": node.name, "bases": bases, "methods": methods})
        elif isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
            args = [a.arg for a in node.args.args]
            symbols.append({"type": "function", "name": node.name, "args": args})
    return sorted(symbols, key=lambda s: s["name"])


def architecture_snapshot():
    return {p.stem: public_symbols(p) for p in casino_modules()}


# ---- Strands model + callback factory ----


def make_model(max_tokens=4096):
    # claude-sonnet-5 rejects the `temperature` request param outright, so it's
    # deliberately not exposed here -- default sampling only.
    from strands.models.anthropic import AnthropicModel

    return AnthropicModel(
        client_args={"api_key": os.environ["ANTHROPIC_API_KEY"]},
        max_tokens=max_tokens,
        model_id=MODEL_ID,
    )


def activity_callback(agent_name: str):
    """A Strands callback_handler that mirrors tool use into the shared
    activity log instead of the default token-by-token console stream, so
    the log stays readable across all three agents interleaving."""
    seen_tools = set()

    def handler(**kwargs):
        tool = kwargs.get("current_tool_use")
        if not tool:
            return
        tool_id = tool.get("toolUseId")
        if not tool_id or tool_id in seen_tools:
            return
        seen_tools.add(tool_id)
        tool_input = tool.get("input") or {}
        target = tool_input.get("path") or tool_input.get("command") or ""
        log(agent_name, f"tool call: {tool.get('name')} {target}".strip())

    return handler
