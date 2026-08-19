"""Evaluates the Anomaly Detection Agent's incident-report traces already
recorded in MLflow, using mlflow.genai.evaluate().

Two scorers, both purely code-based -- no extra LLM-judge calls, so this is
fast and free to re-run:

  - fixture_correctly_identified: the aggressive_20 vs standard_17 pairing
    is a strategy that IS a documented stress-test fixture (see the
    docstring on AggressivePlayerStrategy in casino/strategies.py), not a
    real bug. A good report says so; a bad one describes an unexplained
    defect instead of reading the docstring it was handed.
  - evidence_cites_numbers: the report's evidence field should cite the
    actual breached percentages from the prompt, not just restate the
    pairing name in prose.

This is intentionally narrow rather than a generic "rate 1-5" LLM judge:
these two checks encode something specific we actually know about this
domain (there's exactly one known non-bug anomaly source in this repo), so
a failure here is actionable, not just a vibe score.

Run standalone once there are some anomaly reports to evaluate:
    python3 -m agents.evaluate
"""
import json
import re

import mlflow
from mlflow.entities import Feedback
from mlflow.genai.scorers import scorer

import agents.common  # noqa: F401  (import side effect: configures the MLflow tracking URI)

PAIRING_RE = re.compile(r"strategy pairing (\S+) vs (\S+)")

FIXTURE_KEYWORDS = (
    "fixture",
    "deliberate",
    "stress-test",
    "documented",
    "intentional",
    "expected behavior",
    "not a defect",
    "not a bug",
)


def _parse_report(outputs) -> dict:
    if isinstance(outputs, dict):
        return outputs
    try:
        return json.loads(outputs)
    except (TypeError, ValueError):
        return {}


@scorer
def fixture_correctly_identified(inputs, outputs) -> Feedback:
    # Match the pairing named in "strategy pairing X vs Y", not just any
    # occurrence of "aggressive_20" in the prompt -- the full source of
    # strategies.py (which mentions it in a docstring) is always included,
    # so a naive substring check on the whole prompt is true almost always
    # regardless of which pairing actually triggered this investigation.
    prompt_text = inputs if isinstance(inputs, str) else json.dumps(inputs)
    match = PAIRING_RE.search(prompt_text)
    pairing = match.group(0) if match else ""
    if "aggressive_20" not in pairing:
        return Feedback(value=True, rationale="not the fixture pairing -- not applicable to this check")

    report = _parse_report(outputs)
    cause = (report.get("likely_cause") or "").lower()
    hit = any(keyword in cause for keyword in FIXTURE_KEYWORDS)
    return Feedback(
        value=hit,
        rationale=(
            "correctly attributed the anomaly to the documented aggressive_20 fixture"
            if hit
            else "described the known aggressive_20 fixture as if its cause were unexplained"
        ),
    )


@scorer
def evidence_cites_numbers(outputs) -> Feedback:
    report = _parse_report(outputs)
    evidence = report.get("evidence") or ""
    hit = "%" in evidence
    return Feedback(
        value=hit,
        rationale="evidence cites concrete percentages" if hit else "evidence is vague, with no cited numbers",
    )


def main():
    experiment = mlflow.get_experiment_by_name("casino-agent-layer")
    if experiment is None:
        print("No casino-agent-layer experiment found -- run the orchestrator first.")
        return

    traces = mlflow.search_traces(experiment_ids=[experiment.experiment_id], return_type="list")
    incident_traces = [t for t in traces if "Produce an incident report" in str(t.data.request)]
    print(f"{len(traces)} traces total, {len(incident_traces)} are anomaly incident-report calls")

    if not incident_traces:
        print("No incident-report traces yet -- wait for the Anomaly Detection Agent to fire, then re-run.")
        return

    results = mlflow.genai.evaluate(
        data=incident_traces,
        scorers=[fixture_correctly_identified, evidence_cites_numbers],
    )
    print(results)


if __name__ == "__main__":
    main()
