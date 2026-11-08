# Codelanche AI

> Local AI agents that map repositories, trace dependencies, and predict the blast radius of code changes.

Codelanche AI combines deterministic code analysis with grounded local agents. The scanner establishes what exists and how it is connected; the agents explain those facts without inventing files, symbols, or tests.

**Status:** early MVP. Python receives AST-level analysis. JavaScript and TypeScript receive conservative file/import and top-level symbol analysis.

## Why Codelanche?

A one-line change can trigger an avalanche across APIs, services, schemas, tests, and configuration. Codelanche answers:

- What depends on this file or symbol?
- Which paths are most likely to break?
- Which tests should run first?
- What evidence supports the AI's explanation?

All scanning works offline. AI explanations are optional and run through a local Ollama server by default.

## Quick start

Requirements:

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) or pip
- Ollama only when using `--ai`

```bash
cd codelanche-ai
uv sync --extra dev

uv run codelanche scan .
uv run codelanche impact scan_repository --repo .
```

Ask the local Impact Agent for a grounded explanation:

```bash
ollama pull qwen3:8b
uv run codelanche impact scan_repository --repo . --ai --model qwen3:8b
```

Machine-readable output is available from both analysis commands:

```bash
uv run codelanche scan . --json
uv run codelanche impact scan_repository --repo . --json
```

## Architecture

```text
CLI / future Web UI / future MCP server
                  │
                  ▼
       Programmatic Coordinator
                  │
        ┌─────────┴─────────┐
        ▼                   ▼
Deterministic engine   PydanticAI agents
AST · graph · Git      Impact · Verify
        │                   │
        └─────────┬─────────┘
                  ▼
       Evidence-backed report
```

The orchestration is deliberately programmatic. An LLM does not decide whether a dependency exists. It receives a bounded report, explains it, and is then checked by the verifier.

## Current agent harness

Codelanche uses PydanticAI with Ollama:

- Typed agent outputs
- JSON-schema-constrained local responses
- Provider abstraction for future model backends
- Explicit evidence validation after every model run
- No cloud requirement

The first specialist is the **Impact Agent**. The roadmap adds Mapper, Test, Architect, and dedicated Verifier agents while keeping graph construction deterministic.

## Commands

### `codelanche scan`

Build a repository graph and print its size.

```bash
codelanche scan [REPOSITORY] [--json]
```

### `codelanche impact`

Find reverse dependencies for a file, symbol, or qualified name.

```bash
codelanche impact TARGET [--repo REPOSITORY] [--depth 4] [--json] [--ai]
```

### `codelanche doctor`

Check Python and local Ollama availability.

```bash
codelanche doctor
```

## Safety and trust model

- Repository analysis is read-only.
- Scanning never executes repository code.
- AI is not used to manufacture graph edges.
- Agent citations must resolve to deterministic evidence.
- Agent-recommended tests must exist in the deterministic recommendation set.
- AI is optional; core analysis works without a model.

See [the architecture notes](docs/architecture.md) for the component boundaries and planned MCP interface.

## Development

```bash
uv sync --extra dev
uv run pytest
uv run ruff check .
```

## Roadmap

- [x] Python AST scanner
- [x] TypeScript/JavaScript import scanner
- [x] Reverse dependency traversal
- [x] Deterministic risk score and test recommendations
- [x] Grounded local Impact Agent
- [ ] Tree-sitter adapters with symbol resolution across languages
- [ ] Git diff and branch comparison
- [ ] SQLite graph snapshots and incremental indexing
- [ ] MCP server for Codex, Claude Code, and other coding agents
- [ ] React Flow architecture and blast-radius viewer
- [ ] Evaluation suite for recall, citation validity, and hallucination rate

## License

MIT

