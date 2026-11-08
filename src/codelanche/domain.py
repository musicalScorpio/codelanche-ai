"""Typed domain objects shared by scanning, analysis, and agent layers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

NodeKind = Literal["file", "class", "function", "method"]
EdgeKind = Literal["contains", "imports", "calls"]
RiskLevel = Literal["low", "medium", "high", "critical"]


@dataclass(frozen=True, slots=True)
class CodeNode:
    id: str
    name: str
    qualified_name: str
    kind: NodeKind
    path: str
    line: int
    end_line: int
    language: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CodeEdge:
    source: str
    target: str
    kind: EdgeKind
    path: str
    line: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RepositoryGraph:
    root: Path
    nodes: dict[str, CodeNode] = field(default_factory=dict)
    edges: list[CodeEdge] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_node(self, node: CodeNode) -> None:
        self.nodes[node.id] = node

    def add_edge(self, edge: CodeEdge) -> None:
        if edge.source == edge.target:
            return
        if edge.source not in self.nodes or edge.target not in self.nodes:
            return
        if edge not in self.edges:
            self.edges.append(edge)

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": str(self.root),
            "nodes": [node.to_dict() for node in sorted(self.nodes.values(), key=lambda n: n.id)],
            "edges": [edge.to_dict() for edge in self.edges],
            "warnings": self.warnings,
            "summary": {
                "node_count": len(self.nodes),
                "edge_count": len(self.edges),
                "file_count": sum(node.kind == "file" for node in self.nodes.values()),
            },
        }


@dataclass(frozen=True, slots=True)
class ImpactedNode:
    node: CodeNode
    distance: int
    via: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "node": self.node.to_dict(),
            "distance": self.distance,
            "via": list(self.via),
        }


@dataclass(slots=True)
class ImpactReport:
    query: str
    matched: list[CodeNode]
    impacted: list[ImpactedNode]
    risk: RiskLevel
    score: int
    recommended_tests: list[str]
    warnings: list[str] = field(default_factory=list)

    @property
    def impacted_files(self) -> list[str]:
        paths = {item.node.path for item in self.impacted if item.node.kind == "file"}
        return sorted(paths)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "matched": [node.to_dict() for node in self.matched],
            "impacted": [item.to_dict() for item in self.impacted],
            "impacted_files": self.impacted_files,
            "risk": self.risk,
            "score": self.score,
            "recommended_tests": self.recommended_tests,
            "warnings": self.warnings,
        }

