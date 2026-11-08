import json
from pathlib import Path

from codelanche.cli import main

FIXTURE = Path(__file__).parent / "fixtures" / "sample_app"


def test_scan_json(capsys) -> None:
    main(["scan", str(FIXTURE), "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["file_count"] == 5


def test_impact_text(capsys) -> None:
    main(["impact", "load_user", "--repo", str(FIXTURE)])

    output = capsys.readouterr().out
    assert "Impact: load_user" in output
    assert "tests/test_service.py" in output

