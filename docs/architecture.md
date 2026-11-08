# Architecture

## Design principle

Codelanche separates **facts** from **interpretation**.

The deterministic engine owns repository discovery, parsing, symbol identity, dependency edges, graph traversal, risk inputs, and test discovery. Agents may explain, prioritize, and summarize that evidence, but they cannot add new graph facts.

## Components

### Scanner

`codelanche.scanner` discovers supported source files without importing or executing them. Python is parsed with `ast`; TypeScript and JavaScript use a conservative MVP parser that will be replaced by Tree-sitter adapters.

### Repository graph

Edges point from consumer to dependency:

```text
api.profile_route ──calls──▶ service.get_profile
service.get_profile ──calls──▶ repository.load_user
```

Blast-radius analysis walks those edges in reverse, answering “who depends on the thing that changed?”

### Impact engine

`codelanche.impact` matches a target, performs a bounded reverse traversal, scores risk using deterministic inputs, and identifies relevant tests.

### Agent harness

`codelanche.agents.CodelancheHarness` is a programmatic coordinator built on PydanticAI. The MVP runs one Impact Agent. Its structured result is passed through a verifier that rejects unsupported file and line citations or invented test paths.

## Planned MCP surface

The MCP server will expose narrow, read-only tools:

- `scan_repository`
- `find_symbol`
- `find_callers`
- `find_dependency_path`
- `analyze_change_impact`
- `recommend_tests`
- `compare_branches`

Each tool will return typed evidence. No write or shell-execution tool is planned for the default server.

## Planned specialist roles

| Role | Responsibility | Authority |
| --- | --- | --- |
| Mapper | Explain graph structure and subsystem boundaries | Read-only graph queries |
| Impact | Explain deterministic blast-radius reports | Read-only report |
| Test | Prioritize existing tests and identify coverage gaps | Read-only graph and test index |
| Architect | Describe architecture and branch-level drift | Read-only snapshots |
| Verifier | Reject unsupported claims and citations | Deterministic validation only |

