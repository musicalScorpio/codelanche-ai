"""PydanticAI harness layered over deterministic analysis."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from codelanche.domain import ImpactReport, RepositoryGraph
from codelanche.impact import analyze_impact
from codelanche.scanner import scan_repository


class CodeReference(BaseModel):
    path: str
    line: int = Field(ge=1)
    symbol: str | None = None


class AgentExplanation(BaseModel):
    summary: str
    risk: Literal["low", "medium", "high", "critical"]
    affected_areas: list[str]
    reasoning: list[str]
    recommended_tests: list[str]
    evidence: list[CodeReference]


@dataclass(frozen=True, slots=True)
class HarnessResult:
    report: ImpactReport
    explanation: AgentExplanation | None


class EvidenceVerificationError(ValueError):
    """Raised when an agent cites code outside the deterministic evidence set."""


class AgentRuntimeError(RuntimeError):
    """Raised when the configured local model cannot complete an agent run."""


class CodelancheHarness:
    """Programmatic coordinator for deterministic tools and specialist agents."""

    def __init__(
        self,
        graph: RepositoryGraph,
        *,
        model_name: str | None = None,
        ollama_base_url: str | None = None,
    ) -> None:
        self.graph = graph
        self.model_name = model_name or os.getenv("CODELANCHE_MODEL", "qwen3:8b")
        self.ollama_base_url = ollama_base_url or os.getenv(
            "OLLAMA_BASE_URL", "http://localhost:11434/v1"
        )

    @classmethod
    def from_repository(
        cls,
        root: str | Path,
        *,
        model_name: str | None = None,
        ollama_base_url: str | None = None,
    ) -> CodelancheHarness:
        return cls(
            scan_repository(root),
            model_name=model_name,
            ollama_base_url=ollama_base_url,
        )

    def impact(self, query: str, *, max_depth: int = 4, use_ai: bool = False) -> HarnessResult:
        report = analyze_impact(self.graph, query, max_depth=max_depth)
        if not use_ai or not report.matched:
            return HarnessResult(report=report, explanation=None)
        explanation = self._run_impact_agent(report)
        self.verify_explanation(explanation, report)
        return HarnessResult(report=report, explanation=explanation)

    def verify_explanation(
        self, explanation: AgentExplanation, report: ImpactReport
    ) -> None:
        """Reject unsupported citations and invented test paths."""

        allowed_lines: dict[str, set[int]] = {}
        evidence_nodes = [*report.matched, *(item.node for item in report.impacted)]
        for node in evidence_nodes:
            allowed_lines.setdefault(node.path, set()).update(range(node.line, node.end_line + 1))

        for reference in explanation.evidence:
            if reference.path not in allowed_lines:
                raise EvidenceVerificationError(
                    f"agent cited path outside evidence set: {reference.path}"
                )
            if reference.line not in allowed_lines[reference.path]:
                raise EvidenceVerificationError(
                    f"agent cited unsupported line: {reference.path}:{reference.line}"
                )

        known_tests = set(report.recommended_tests)
        invented = set(explanation.recommended_tests) - known_tests
        if invented:
            raise EvidenceVerificationError(
                f"agent recommended tests not found by deterministic analysis: {sorted(invented)}"
            )

    def _run_impact_agent(self, report: ImpactReport) -> AgentExplanation:
        from pydantic_ai import Agent
        from pydantic_ai.models.ollama import OllamaModel
        from pydantic_ai.output import NativeOutput
        from pydantic_ai.providers.ollama import OllamaProvider

        model = OllamaModel(
            self.model_name,
            provider=OllamaProvider(base_url=self.ollama_base_url),
        )
        agent = Agent(
            model,
            output_type=NativeOutput(AgentExplanation),
            model_settings={"max_tokens": 2048, "temperature": 0.1},
            system_prompt=(
                "You are Codelanche AI's Impact Agent. Explain only the supplied deterministic "
                "analysis. Never invent files, symbols, tests, or line numbers. Keep the "
                "deterministic risk rating unchanged. Cite the strongest supporting nodes."
            ),
        )
        prompt = (
            "Explain this change-impact report for a software engineer. Return only evidence "
            "present in the report.\n\n"
            f"{json.dumps(_agent_payload(report), indent=2)}"
        )
        try:
            return agent.run_sync(prompt).output
        except Exception as exc:
            raise AgentRuntimeError(
                "local Impact Agent failed; run `codelanche doctor`, verify Ollama is running, "
                f"and confirm model {self.model_name!r} is installed. Provider error: {exc}"
            ) from exc


def _agent_payload(report: ImpactReport) -> dict[str, object]:
    """Create a bounded evidence packet suitable for a local model context window."""

    def node_evidence(node) -> dict[str, object]:
        return {
            "path": node.path,
            "line": node.line,
            "end_line": node.end_line,
            "symbol": node.qualified_name,
            "kind": node.kind,
        }

    return {
        "query": report.query,
        "risk": report.risk,
        "score": report.score,
        "matched": [node_evidence(node) for node in report.matched[:10]],
        "impacted": [
            {**node_evidence(item.node), "distance": item.distance}
            for item in report.impacted[:40]
        ],
        "recommended_tests": report.recommended_tests,
    }

