from pathlib import Path

from codelanche.scanner import scan_repository

FIXTURE = Path(__file__).parent / "fixtures" / "sample_app"


def test_scanner_builds_file_symbol_import_and_call_edges() -> None:
    graph = scan_repository(FIXTURE)

    files = {node.path for node in graph.nodes.values() if node.kind == "file"}
    assert "app/repository.py" in files
    assert "app/service.py" in files
    assert "app/api.py" in files

    symbols = {node.qualified_name for node in graph.nodes.values() if node.kind != "file"}
    assert "app.repository.load_user" in symbols
    assert "app.service.get_profile" in symbols
    assert "app.api.profile_route" in symbols

    edge_kinds = {edge.kind for edge in graph.edges}
    assert {"contains", "imports", "calls"} <= edge_kinds


def test_scanner_ignores_virtual_environment_directories(tmp_path: Path) -> None:
    source = tmp_path / "main.py"
    source.write_text("def visible():\n    return True\n", encoding="utf-8")
    ignored = tmp_path / ".venv" / "hidden.py"
    ignored.parent.mkdir()
    ignored.write_text("def hidden():\n    return True\n", encoding="utf-8")

    graph = scan_repository(tmp_path)

    paths = {node.path for node in graph.nodes.values()}
    assert "main.py" in paths
    assert ".venv/hidden.py" not in paths


def test_typescript_relative_imports_are_resolved(tmp_path: Path) -> None:
    source = tmp_path / "src"
    source.mkdir()
    (source / "service.ts").write_text(
        "export function getProfile() { return {}; }\n", encoding="utf-8"
    )
    (source / "api.ts").write_text(
        "import { getProfile } from './service';\n"
        "export function route() { return getProfile(); }\n",
        encoding="utf-8",
    )

    graph = scan_repository(tmp_path)

    imports = {
        (graph.nodes[edge.source].path, graph.nodes[edge.target].path)
        for edge in graph.edges
        if edge.kind == "imports"
    }
    assert ("src/api.ts", "src/service.ts") in imports

