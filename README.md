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
  - Transports: both local standard I/O (`stdio`) and remote Server-Sent Events (`sse`)
- AST-aware source code extraction for Python (`ast`) and TypeScript (`interface`, `type`, `function`, `class` signatures with JSDoc).
- Hybrid search (BM25 + Dense Vectors via Reciprocal Rank Fusion) and whole-section preservation with strict token budgeting.

The engine ingests OpenAPI 3.x, Markdown/MDX, and raw source code across Python and TypeScript. Automated agent evaluation benchmarks remain planned work.

## High‑level Architecture

Sources (OpenAPI, Markdown, Python & TS ASTs) → Ingestion → IR → Transformation & Compression
(Noise stripping, signature extraction, token-budgeting, vector embeddings) → Dual outputs:
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

- Hybrid search: SQLite FTS5 (BM25) + dense vector embeddings merged via Reciprocal Rank Fusion (RRF)
- Deterministic path-and-method exact API lookup with close-match route suggestions on missing endpoints
- OpenAPI operations and Markdown documents remain whole during retrieval
- Token budgeting supports both `cl100k_base` and `o200k_base` tokenizers via `tiktoken`

## Roadmap & Milestones

### Implemented
- OpenAPI 3.x and Markdown/MDX ingestion
- Python AST extraction (`ast`) for classes, typed attributes, and function/method signatures
- TypeScript AST extraction for `interface`, `type`, `function`, and `class` declarations with JSDoc
- Static artifacts generation (`/llms.txt`, `/llms-small.txt`, `/llms-full.txt`)
- Hybrid search (BM25 + Dense Vectors) with Reciprocal Rank Fusion
- Multi-tokenizer support (`cl100k_base` and `o200k_base`)
- Dual MCP server transports: stdio and SSE (HTTP) with manifest, search, and exact API lookup

### Next (Phase 4)
- Automated token reduction benchmark suite (>60% reduction target)
- Agent task success evaluation harness and MCP conformance verification

### Long term
- Ecosystem: exporters (SDKs), adapters for common docs stacks (mkdocs, swagger), and production deployment patterns

## Suggested Tech Stack

- Runtime: Python 3.11+ and the official MCP SDK
- Parsing: PyYAML for OpenAPI YAML, Python `ast`, TypeScript regex/AST parser, built-in JSON/MDX processing
- Storage & search: SQLite FTS5 (BM25) + embedded vector similarity
- Protocol: official MCP SDK for Python (`stdio` and `sse` transports with Starlette/Uvicorn)
- Tokenization: tiktoken (`cl100k_base` and `o200k_base`)

## How to contribute

- Python 3.11+ is required.
- Install the project and development dependencies with `python -m pip install -e ".[dev]"`.
- Build artifacts from the included sample sources (OpenAPI, Markdown, Python, and TypeScript):

  ```powershell
  living-docs build --openapi examples\openapi.yaml --markdown examples\docs --python examples\src\client.py --typescript examples\src\types.ts --output build --project-name "Example Tasks API"
  ```

  This creates `llms.txt`, `llms-small.txt`, `llms-full.txt`, and `docs-index.json`.
- Start the MCP server over stdio:

  ```powershell
  living-docs serve --index build\docs-index.json --transport stdio
  ```

- Or run the MCP server over SSE for remote clients:

  ```powershell
  living-docs serve --index build\docs-index.json --transport sse --host 127.0.0.1 --port 8000
  ```

- Run the tests with `python -m pytest`.

Current boundaries: external OpenAPI references are rejected; cyclic local references are retained as `$ref`s at the recursion boundary; semantic units are kept whole (oversized search results are omitted rather than cut); automated agent evaluation benchmarks are the next milestone.

## License & Contact

Add your chosen license file (e.g., LICENSE.md) and maintainers/contact info here.
