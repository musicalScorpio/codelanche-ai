from pathlib import Path

import pytest

from codelanche.agents.harness import (
    AgentExplanation,
    CodelancheHarness,
    CodeReference,
    EvidenceVerificationError,
)

FIXTURE = Path(__file__).parent / "fixtures" / "sample_app"


def test_harness_runs_without_model() -> None:
    harness = CodelancheHarness.from_repository(FIXTURE)

    result = harness.impact("load_user")

    assert result.report.matched
    assert result.explanation is None


def test_verifier_rejects_invented_evidence() -> None:
    harness = CodelancheHarness.from_repository(FIXTURE)
    report = harness.impact("load_user").report
    explanation = AgentExplanation(
        summary="Invented claim",
        risk=report.risk,
        affected_areas=[],
        reasoning=[],
        recommended_tests=report.recommended_tests,
        evidence=[CodeReference(path="invented.py", line=1)],
    )

    with pytest.raises(EvidenceVerificationError, match="outside evidence set"):
        harness.verify_explanation(explanation, report)


def test_verifier_accepts_grounded_evidence() -> None:
    harness = CodelancheHarness.from_repository(FIXTURE)
    report = harness.impact("load_user").report
    source = report.matched[0]
    explanation = AgentExplanation(
        summary="Grounded claim",
        risk=report.risk,
        affected_areas=[source.path],
        reasoning=["The repository function has downstream consumers."],
        recommended_tests=report.recommended_tests,
        evidence=[CodeReference(path=source.path, line=source.line, symbol=source.name)],
    )

    harness.verify_explanation(explanation, report)

