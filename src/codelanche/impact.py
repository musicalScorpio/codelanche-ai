"""Deterministic blast-radius and test-selection analysis."""

from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path

from codelanche.domain import CodeEdge, CodeNode, ImpactedNode, ImpactReport, RepositoryGraph


def analyze_impact(graph: RepositoryGraph, query: str, max_depth: int = 4) -> ImpactReport:
    """Find nodes that depend on the queried file or symbol.

    Edges point from consumer to dependency. Impact therefore walks the graph in
    reverse, preserving the evidence path used to reach each consumer.
    """

    if max_depth < 1:
        raise ValueError("max_depth must be at least 1")

    matched = _match_nodes(graph, query)
    if not matched:
        return ImpactReport(
            query=query,
            matched=[],
            impacted=[],
            risk="low",
            score=0,
            recommended_tests=[],
            warnings=[f"no file or symbol matched {query!r}"],
        )

    reverse: dict[str, list[CodeEdge]] = defaultdict(list)
    for edge in graph.edges:
        reverse[edge.target].append(edge)

    origins = {node.id for node in matched}
    queue: deque[tuple[str, int, tuple[str, ...]]] = deque(
        (node.id, 0, (node.id,)) for node in matched
    )
    best_distance: dict[str, int] = {node.id: 0 for node in matched}
    impacted: dict[str, ImpactedNode] = {}

    while queue:
        current, distance, route = queue.popleft()
        if distance >= max_depth:
            continue
        for edge in reverse.get(current, []):
            candidate = edge.source
            candidate_distance = distance + 1
            if candidate in best_distance and best_distance[candidate] <= candidate_distance:
                continue
            best_distance[candidate] = candidate_distance
            candidate_route = (*route, candidate)
            queue.append((candidate, candidate_distance, candidate_route))
            if candidate not in origins:
                impacted[candidate] = ImpactedNode(
                    node=graph.nodes[candidate],
                    distance=candidate_distance,
                    via=candidate_route,
                )

    ordered = sorted(
        impacted.values(),
        key=lambda item: (item.distance, item.node.path, item.node.line, item.node.name),
    )
    recommended_tests = _recommend_tests(graph, matched, ordered)
    score = _risk_score(matched, ordered, recommended_tests)
    return ImpactReport(
        query=query,
        matched=matched,
        impacted=ordered,
        risk=_risk_level(score),
        score=score,
        recommended_tests=recommended_tests,
        warnings=[],
    )


def _match_nodes(graph: RepositoryGraph, query: str) -> list[CodeNode]:
    normalized = query.removeprefix("./").replace("\\", "/")
    exact = [
        node
        for node in graph.nodes.values()
        if normalized in {node.id, node.path, node.qualified_name}
    ]
    if exact:
        return sorted(exact, key=lambda node: (node.path, node.line))

    by_name = [node for node in graph.nodes.values() if node.name == query]
    if by_name:
        return sorted(by_name, key=lambda node: (node.path, node.line))

    lowered = query.casefold()
    fuzzy = [
        node
        for node in graph.nodes.values()
        if lowered in node.qualified_name.casefold() or lowered in node.path.casefold()
    ]
    return sorted(fuzzy, key=lambda node: (node.path, node.line))[:20]


def _recommend_tests(
    graph: RepositoryGraph, matched: list[CodeNode], impacted: list[ImpactedNode]
) -> list[str]:
    relevant_paths = {node.path for node in matched}
    relevant_paths.update(item.node.path for item in impacted)
    source_stems = {
        Path(path).stem.removeprefix("test_").removesuffix("_test") for path in relevant_paths
    }

    tests: set[str] = set()
    for node in graph.nodes.values():
        if node.kind != "file" or not _is_test_path(node.path):
            continue
        stem = Path(node.path).stem.removeprefix("test_").removesuffix("_test")
        if node.path in relevant_paths or stem in source_stems:
            tests.add(node.path)

    reverse_import_targets = {node.id for node in matched}
    reverse_import_targets.update(item.node.id for item in impacted)
    for edge in graph.edges:
        source = graph.nodes.get(edge.source)
        if (
            edge.target in reverse_import_targets
            and source is not None
            and source.kind == "file"
            and _is_test_path(source.path)
        ):
            tests.add(source.path)
    return sorted(tests)


def _is_test_path(path: str) -> bool:
    parts = Path(path).parts
    name = Path(path).name
    if "fixtures" in parts:
        return False
    return "tests" in parts or name.startswith("test_") or name.endswith((".test.ts", ".spec.ts"))


def _risk_score(
    matched: list[CodeNode], impacted: list[ImpactedNode], recommended_tests: list[str]
) -> int:
    impacted_files = {item.node.path for item in impacted}
    public_surface = any(
        token in node.path.casefold()
        for node in matched
        for token in ("api", "route", "schema", "migration", "auth", "config")
    )
    score = min(len(impacted_files) * 7, 56)
    score += min(len(impacted) * 2, 20)
    score += 14 if public_surface else 0
    score += 10 if impacted_files and not recommended_tests else 0
    return min(score, 100)


def _risk_level(score: int) -> str:
    if score >= 75:
        return "critical"
    if score >= 45:
        return "high"
    if score >= 20:
        return "medium"
    return "low"

