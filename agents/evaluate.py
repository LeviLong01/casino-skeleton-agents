"""Evaluates the agent layer's MLflow traces with mlflow.genai.evaluate().

Two passes:

  1. General quality, across all three agents' traces, using two MLflow
     built-in LLM judges:
       - RelevanceToQuery: does each agent call's output actually address
         what it was asked (needs inputs/outputs on the root span, which
         every trace here has)?
       - ToolCallEfficiency: for the calls that use real tools (the Test
         Writer Agent's file/shell tools, the Documentation Agent's
         file-editing call), are there redundant/duplicate tool calls?
         Traces with no TOOL-type span (the plain structured-output calls
         -- significance judging, incident-report generation) are outside
         its scope and get filtered out before this pass.

  2. Anomaly Detection Agent incident reports specifically, with two
     purely code-based scorers -- no extra LLM-judge calls, so cheap to
     re-run:
       - fixture_correctly_identified: the aggressive_20 vs standard_17
         pairing is a strategy that IS a documented stress-test fixture
         (see the docstring on AggressivePlayerStrategy in
         casino/strategies.py), not a real bug. A good report says so; a
         bad one describes an unexplained defect instead of reading the
         docstring it was handed.
       - evidence_cites_numbers: the report's evidence field should cite
         the actual breached percentages from the prompt, not just
         restate the pairing name in prose.

     This second pass is intentionally narrow rather than another generic
     LLM judge: these two checks encode something specific we actually
     know about this domain (there's exactly one known non-bug anomaly
     source in this repo), so a failure here is actionable, not a vibe
     score.

Run standalone:
    python3 -m agents.evaluate
"""
import json
import re

import mlflow
from mlflow.entities import Feedback
from mlflow.genai.scorers import RelevanceToQuery, ToolCallEfficiency, scorer

import agents.common  # noqa: F401  (import side effect: configures the MLflow tracking URI)
from agents.common import MODEL_ID

JUDGE_MODEL = f"anthropic:/{MODEL_ID}"

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


def _has_tool_span(trace) -> bool:
    return any(getattr(span, "span_type", None) == "TOOL" for span in trace.data.spans)


def evaluate_general_quality(traces):
    print(f"\n== General quality across all agents: RelevanceToQuery, ToolCallEfficiency ==")
    print(f"{len(traces)} traces total")
    print(mlflow.genai.evaluate(data=traces, scorers=[RelevanceToQuery(model=JUDGE_MODEL)]))

    # Every trace turns out to have at least one TOOL span, even the plain
    # structured-output calls -- Strands implements structured_output_model
    # as a synthetic tool call under the hood -- so this filter ends up
    # keeping the full set rather than narrowing to "real" tool-using calls.
    # Left in as documentation of that, and as a real guard if that ever
    # changes.
    tool_traces = [t for t in traces if _has_tool_span(t)]
    print(f"{len(tool_traces)} traces contain at least one TOOL span (required by ToolCallEfficiency)")
    if tool_traces:
        print(mlflow.genai.evaluate(data=tool_traces, scorers=[ToolCallEfficiency(model=JUDGE_MODEL)]))
    else:
        print("  none yet -- skipping (fires once the Test Writer or Documentation Agent uses a tool)")


def evaluate_anomaly_reports(traces):
    print(f"\n== Anomaly Detection Agent incident reports: fixture_correctly_identified, evidence_cites_numbers ==")
    incident_traces = [t for t in traces if "Produce an incident report" in str(t.data.request)]
    print(f"{len(incident_traces)} incident-report traces")
    if not incident_traces:
        print("  none yet -- wait for the Anomaly Detection Agent to fire, then re-run")
        return
    results = mlflow.genai.evaluate(
        data=incident_traces,
        scorers=[fixture_correctly_identified, evidence_cites_numbers],
    )
    print(results)


def main():
    experiment = mlflow.get_experiment_by_name("casino-agent-layer")
    if experiment is None:
        print("No casino-agent-layer experiment found -- run the orchestrator first.")
        return

    traces = mlflow.search_traces(experiment_ids=[experiment.experiment_id], return_type="list")
    if not traces:
        print("No traces recorded yet -- run the orchestrator first.")
        return

    evaluate_general_quality(traces)
    evaluate_anomaly_reports(traces)


if __name__ == "__main__":
    main()
