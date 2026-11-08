from pathlib import Path

from codelanche.impact import analyze_impact
from codelanche.scanner import scan_repository

FIXTURE = Path(__file__).parent / "fixtures" / "sample_app"


def test_repository_change_reaches_service_api_and_test() -> None:
    graph = scan_repository(FIXTURE)

    report = analyze_impact(graph, "load_user")

    impacted_paths = {item.node.path for item in report.impacted}
    assert "app/service.py" in impacted_paths
    assert "app/api.py" in impacted_paths
    assert "tests/test_service.py" in impacted_paths
    assert report.risk in {"medium", "high", "critical"}
    assert report.recommended_tests == ["tests/test_service.py"]


def test_unknown_target_returns_actionable_warning() -> None:
    graph = scan_repository(FIXTURE)

    report = analyze_impact(graph, "does_not_exist")

    assert report.matched == []
    assert report.score == 0
    assert report.warnings == ["no file or symbol matched 'does_not_exist'"]


def test_depth_must_be_positive() -> None:
    graph = scan_repository(FIXTURE)

    try:
        analyze_impact(graph, "load_user", max_depth=0)
    except ValueError as exc:
        assert "at least 1" in str(exc)
    else:
        raise AssertionError("expected max_depth validation to fail")

