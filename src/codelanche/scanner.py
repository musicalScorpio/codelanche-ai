"""Deterministic repository scanners.

The initial release intentionally uses the Python standard library. Tree-sitter
adapters can be added without changing the graph or agent interfaces.
"""

from __future__ import annotations

import ast
import posixpath
import re
from dataclasses import dataclass, field
from pathlib import Path

from codelanche.domain import CodeEdge, CodeNode, RepositoryGraph

SUPPORTED_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx"}
IGNORED_DIRECTORIES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "build",
    "dist",
    "node_modules",
    "venv",
}


@dataclass(slots=True)
class _PendingEdge:
    source: str
    target_name: str
    kind: str
    path: str
    line: int
    module_hint: str | None = None


@dataclass(slots=True)
class _ScanState:
    graph: RepositoryGraph
    module_to_file: dict[str, str] = field(default_factory=dict)
    symbols_by_name: dict[str, list[str]] = field(default_factory=dict)
    symbols_by_qualified_name: dict[str, str] = field(default_factory=dict)
    pending: list[_PendingEdge] = field(default_factory=list)

    def add_node(self, node: CodeNode) -> None:
        self.graph.add_node(node)
        self.symbols_by_name.setdefault(node.name, []).append(node.id)
        self.symbols_by_qualified_name[node.qualified_name] = node.id


def scan_repository(root: str | Path) -> RepositoryGraph:
    """Scan a repository into a dependency graph.

    Python receives AST-level symbol, import, and call analysis. JavaScript and
    TypeScript receive a conservative import/export scan in the MVP.
    """

    resolved_root = Path(root).expanduser().resolve()
    if not resolved_root.exists():
        raise FileNotFoundError(f"repository does not exist: {resolved_root}")
    if not resolved_root.is_dir():
        raise NotADirectoryError(f"repository is not a directory: {resolved_root}")

    graph = RepositoryGraph(root=resolved_root)
    state = _ScanState(graph=graph)
    files = sorted(_iter_source_files(resolved_root))

    for path in files:
        relative = path.relative_to(resolved_root).as_posix()
        file_id = _file_id(relative)
        language = "python" if path.suffix == ".py" else "typescript"
        state.add_node(
            CodeNode(
                id=file_id,
                name=path.name,
                qualified_name=relative,
                kind="file",
                path=relative,
                line=1,
                end_line=_line_count(path),
                language=language,
            )
        )
        if path.suffix == ".py":
            state.module_to_file[_module_name(relative)] = file_id

    for path in files:
        relative = path.relative_to(resolved_root).as_posix()
        if path.suffix == ".py":
            _scan_python(path, relative, state)
        else:
            _scan_javascript(path, relative, state)

    _resolve_pending_edges(state)
    return graph


def _iter_source_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in SUPPORTED_SUFFIXES:
            continue
        if any(part in IGNORED_DIRECTORIES for part in path.relative_to(root).parts):
            continue
        yield path


def _line_count(path: Path) -> int:
    try:
        with path.open("r", encoding="utf-8") as source:
            return sum(1 for _ in source) or 1
    except UnicodeDecodeError:
        return 1


def _file_id(relative: str) -> str:
    return f"file:{relative}"


def _symbol_id(relative: str, qualified_name: str) -> str:
    return f"symbol:{relative}:{qualified_name}"


def _module_name(relative: str) -> str:
    path = Path(relative)
    parts = list(path.with_suffix("").parts)
    if parts and parts[0] == "src":
        parts = parts[1:]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


class _PythonVisitor(ast.NodeVisitor):
    def __init__(self, relative: str, state: _ScanState) -> None:
        self.relative = relative
        self.state = state
        self.file_id = _file_id(relative)
        self.module = _module_name(relative)
        self.scope: list[str] = []
        self.scope_ids: list[str] = []
        self.import_aliases: dict[str, str] = {}

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            local_name = alias.asname or alias.name.split(".")[0]
            self.import_aliases[local_name] = alias.name
            self.state.pending.append(
                _PendingEdge(
                    source=self.file_id,
                    target_name=alias.name,
                    module_hint=alias.name,
                    kind="imports",
                    path=self.relative,
                    line=node.lineno,
                )
            )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = self._absolute_import(node.module or "", node.level)
        self.state.pending.append(
            _PendingEdge(
                source=self.file_id,
                target_name=module,
                module_hint=module,
                kind="imports",
                path=self.relative,
                line=node.lineno,
            )
        )
        for alias in node.names:
            if alias.name == "*":
                continue
            local_name = alias.asname or alias.name
            qualified = f"{module}.{alias.name}" if module else alias.name
            self.import_aliases[local_name] = qualified

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._visit_definition(node, "class")

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        kind = "method" if self.scope and self._current_scope_is_class() else "function"
        self._visit_definition(node, kind)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        kind = "method" if self.scope and self._current_scope_is_class() else "function"
        self._visit_definition(node, kind)

    def visit_Call(self, node: ast.Call) -> None:
        target_name = _call_name(node.func)
        if target_name:
            source = self.scope_ids[-1] if self.scope_ids else self.file_id
            root_name = target_name.split(".")[0]
            alias_target = self.import_aliases.get(root_name)
            if alias_target:
                remainder = target_name[len(root_name) :]
                target_name = f"{alias_target}{remainder}"
            self.state.pending.append(
                _PendingEdge(
                    source=source,
                    target_name=target_name,
                    kind="calls",
                    path=self.relative,
                    line=node.lineno,
                )
            )
        self.generic_visit(node)

    def _visit_definition(
        self, node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef, kind: str
    ) -> None:
        name = node.name
        qualified_parts = [self.module, *self.scope, name]
        qualified_name = ".".join(part for part in qualified_parts if part)
        node_id = _symbol_id(self.relative, qualified_name)
        symbol = CodeNode(
            id=node_id,
            name=name,
            qualified_name=qualified_name,
            kind=kind,  # type: ignore[arg-type]
            path=self.relative,
            line=getattr(node, "lineno", 1),
            end_line=getattr(node, "end_lineno", getattr(node, "lineno", 1)),
            language="python",
        )
        self.state.add_node(symbol)
        parent = self.scope_ids[-1] if self.scope_ids else self.file_id
        self.state.graph.add_edge(
            CodeEdge(
                source=parent,
                target=node_id,
                kind="contains",
                path=self.relative,
                line=symbol.line,
            )
        )
        self.scope.append(name)
        self.scope_ids.append(node_id)
        self.generic_visit(node)
        self.scope.pop()
        self.scope_ids.pop()

    def _current_scope_is_class(self) -> bool:
        if not self.scope_ids:
            return False
        parent = self.state.graph.nodes.get(self.scope_ids[-1])
        return parent is not None and parent.kind == "class"

    def _absolute_import(self, module: str, level: int) -> str:
        if level == 0:
            return module
        current = self.module.split(".")
        package = current if self.relative.endswith("/__init__.py") else current[:-1]
        trim = max(level - 1, 0)
        if trim:
            package = package[:-trim]
        return ".".join([*package, *([module] if module else [])])


def _scan_python(path: Path, relative: str, state: _ScanState) -> None:
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=relative)
    except (UnicodeDecodeError, SyntaxError) as exc:
        state.graph.warnings.append(f"unable to parse {relative}: {exc}")
        return
    _PythonVisitor(relative, state).visit(tree)


IMPORT_RE = re.compile(
    r"(?:import\s+(?:[^;]*?\s+from\s+)?|require\s*\()\s*['\"](?P<module>[^'\"]+)['\"]"
)
DEFINITION_RE = re.compile(
    r"^\s*(?:export\s+)?(?:async\s+)?(?P<kind>function|class)\s+(?P<name>[A-Za-z_$][\w$]*)",
    re.MULTILINE,
)


def _scan_javascript(path: Path, relative: str, state: _ScanState) -> None:
    try:
        source = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        state.graph.warnings.append(f"unable to parse {relative}: {exc}")
        return

    file_id = _file_id(relative)
    for match in DEFINITION_RE.finditer(source):
        name = match.group("name")
        line = source.count("\n", 0, match.start()) + 1
        kind = "class" if match.group("kind") == "class" else "function"
        qualified_name = f"{relative}:{name}"
        node_id = _symbol_id(relative, qualified_name)
        state.add_node(
            CodeNode(
                id=node_id,
                name=name,
                qualified_name=qualified_name,
                kind=kind,
                path=relative,
                line=line,
                end_line=line,
                language="typescript",
            )
        )
        state.graph.add_edge(
            CodeEdge(
                source=file_id,
                target=node_id,
                kind="contains",
                path=relative,
                line=line,
            )
        )

    for match in IMPORT_RE.finditer(source):
        module = match.group("module")
        line = source.count("\n", 0, match.start()) + 1
        target = _resolve_js_import(relative, module, state.graph.nodes)
        if target:
            state.graph.add_edge(
                CodeEdge(
                    source=file_id,
                    target=target,
                    kind="imports",
                    path=relative,
                    line=line,
                )
            )


def _resolve_js_import(relative: str, module: str, nodes: dict[str, CodeNode]) -> str | None:
    if not module.startswith("."):
        return None
    base = posixpath.normpath((Path(relative).parent / module).as_posix())
    candidates = [
        base,
        *(f"{base}{suffix}" for suffix in (".ts", ".tsx", ".js", ".jsx")),
        *(f"{base}/index{suffix}" for suffix in (".ts", ".tsx", ".js", ".jsx")),
    ]
    for candidate in candidates:
        normalized = Path(candidate).as_posix()
        node_id = _file_id(normalized)
        if node_id in nodes:
            return node_id
    return None


def _call_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


def _resolve_pending_edges(state: _ScanState) -> None:
    for pending in state.pending:
        target: str | None = None
        if pending.kind == "imports" and pending.module_hint:
            target = _resolve_module(pending.module_hint, state.module_to_file)
        elif pending.kind == "calls":
            target = _resolve_symbol(pending.target_name, state)
        if target:
            state.graph.add_edge(
                CodeEdge(
                    source=pending.source,
                    target=target,
                    kind=pending.kind,  # type: ignore[arg-type]
                    path=pending.path,
                    line=pending.line,
                )
            )


def _resolve_module(module: str, module_to_file: dict[str, str]) -> str | None:
    current = module
    while current:
        if current in module_to_file:
            return module_to_file[current]
        current = current.rsplit(".", 1)[0] if "." in current else ""
    return None


def _resolve_symbol(name: str, state: _ScanState) -> str | None:
    if name in state.symbols_by_qualified_name:
        return state.symbols_by_qualified_name[name]
    suffix_matches = [
        node_id
        for qualified_name, node_id in state.symbols_by_qualified_name.items()
        if qualified_name.endswith(f".{name}")
    ]
    if len(suffix_matches) == 1:
        return suffix_matches[0]
    simple_name = name.rsplit(".", 1)[-1]
    matches = state.symbols_by_name.get(simple_name, [])
    return matches[0] if len(matches) == 1 else None
