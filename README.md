# LLM‑Optimized Living Documentation Engine

TL;DR — A documentation architecture and runtime that transforms human‑centric docs and API specs into compact, machine‑native artifacts (static /llms.txt files and a Model Context Protocol (MCP) server) so LLMs and agentic systems can discover, reason about, and call APIs with minimal token overhead.

Status: Early implementation — the first local build and MCP stdio vertical slice is available.

## Why this exists

Human‑facing documentation (rich layouts, screenshots, conversational prose) is great for people but wasteful for LLMs and autonomous agents. That noise causes:
- massive token overhead,
- implicit/ambiguous API contracts,
- loss of structural anchors that models need to be deterministic.

This project defines a pipeline and runtime to produce documentation optimized for machine consumption: explicit schemas, compact context blocks, dual static/dynamic access patterns, and MCP tooling.

## What the Engine Provides

- Static, edge-friendly artifacts:
  - `/llms.txt` — structured index & annotated directory of documentation blocks
  - `/llms-small.txt` — compact core signatures and primary endpoints
  - `/llms-full.txt` — full reference optimized for bulk preloading
- MCP Server (Model Context Protocol):
  - Resource: `docs://manifest` (index + token metrics)
  - Tools: `search_docs(query, max_tokens)`, `get_api_spec(endpoint_path, method)` (deterministic, schema-first)
- Whole-operation API retrieval and complete-document Markdown results; oversized search results are omitted rather than truncated.

The current implementation ingests OpenAPI 3.x and Markdown/MDX. Language AST extraction, dense-vector retrieval, and HTTP transports remain planned work.

## High‑level Architecture

Sources (OpenAPI and Markdown repos) → Ingestion → IR → Transformation & Compression
(Noise stripping, signature extraction, token-budgeting) → Dual outputs:
- Static files (`/llms*.txt`) for fast context ingestion
- MCP server for interactive, token-budgeted exploration

## Core Design Principles

- Semantic-first: explicit, machine‑readable structure over visual layout.
- Token-efficient: minimize noise, prioritize signatures and constraints.
- Deterministic: preserve complete schema units so returned context is unambiguous.
- Dual delivery: static manifests for single-shot contexts + dynamic MCP tools for interactive agent workflows.

## Minimal Example: docs://manifest (illustrative)

{
  "uri": "docs://manifest",
  "version": "1.0.0",
  "total_tokens": 42150,
  "sections": [
    { "id": "query-api", "title": "HogQL Query API", "path": "/api/query", "tokens": 1240 },
    { "id": "capture-api", "title": "Event Capture API", "path": "/api/capture", "tokens": 850 }
  ]
}

## Current retrieval and tokenization

- SQLite FTS5/BM25 search plus exact path-and-method API lookup
- OpenAPI operations and Markdown documents remain whole during retrieval
- Exact local token counts use `cl100k_base`; dense vectors and `o200k_base` support are future extensions

## Roadmap & Milestones

### Implemented
- OpenAPI 3.x and Markdown/MDX ingestion
- Static artifacts and MCP stdio server with manifest, search, and exact API lookup
- Token-budgeted whole-section search and compact-reference output

### Next
- Finalize the canonical `/llms.txt` format
- Add TypeScript/Python AST extraction and language-aware semantic chunking
- Add dense-vector retrieval, HTTP transport, and agent evaluation

### Long term
- Ecosystem: exporters (SDKs), adapters for common docs stacks (mkdocs, swagger), and production deployment patterns

## Suggested Tech Stack (provisional)

- Runtime: Python 3.11+ and the official MCP SDK
- Parsing: PyYAML for OpenAPI YAML, built-in JSON and Markdown/MDX processing
- Storage & search: SQLite FTS5/BM25 (dense-vector storage remains planned)
- Protocol: official MCP SDK for Python
- Tokenization: tiktoken (`cl100k_base`)

## How to contribute

- Python 3.11+ is required.
- Install the project and development dependencies with `python -m pip install -e ".[dev]"`.
- Build artifacts from the included sample sources:

  ```powershell
  living-docs build --openapi examples\openapi.yaml --markdown examples\docs --output build --project-name "Example Tasks API"
  ```

  This creates `llms.txt`, `llms-small.txt`, `llms-full.txt`, and `docs-index.json`.
- Start the MCP server over stdio with `living-docs serve --index build\docs-index.json`.
- Run the tests with `python -m pytest`.

The initial slice supports OpenAPI 3.x JSON/YAML files (including local `$ref`s), Markdown/MDX cleanup, `cl100k_base` token counts, static output generation, SQLite FTS5/BM25 search, and the `docs://manifest`, `search_docs`, and `get_api_spec` MCP surfaces.

Current boundaries: external OpenAPI references are rejected; cyclic local references are retained as `$ref`s at the recursion boundary; semantic units are kept whole (oversized search results are omitted rather than cut); dense-vector retrieval, TypeScript/Python AST extraction, HTTP/SSE serving, and agent evaluation are not implemented yet.

## License & Contact

Add your chosen license file (e.g., LICENSE.md) and maintainers/contact info here.
