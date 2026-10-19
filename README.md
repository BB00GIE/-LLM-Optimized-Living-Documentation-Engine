# LLM‑Optimized Living Documentation Engine

TL;DR — A documentation architecture and runtime that transforms human‑centric docs and API specs into compact, machine‑native artifacts (static /llms.txt files and a Model Context Protocol (MCP) server) so LLMs and agentic systems can discover, reason about, and call APIs with minimal token overhead.

Status: Spec / design phase — implementation not yet started. This repository currently contains the project specification and design documents.

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
- AST-aware ingestion and chunking to avoid truncated schemas and reduce hallucinations.

## High‑level Architecture

Sources (OpenAPI, Markdown repos, AST/docstrings) → Ingestion → IR → Transformation & Compression
(Noise stripping, signature extraction, token-budgeting, AST-aware chunking) → Dual outputs:
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

## Why this is different

- Path-indexed + hybrid search (BM25 + dense vectors) for exactness + robustness
- AST-aware chunking so function signatures and JSON schemas are never split
- Token-budgeted outputs to match real model tokenizers (`cl100k_base`, `o200k_base`)

## Roadmap & Milestones

### Short term
- Finalize spec and canonical `/llms.txt` format
- Implement ingestion prototypes for OpenAPI and Markdown
- Build AST-aware chunker and token-budgeting utilities

### Medium term
- Implement MCP server (stdio + SSE transports)
- Implement hybrid search with sqlite-vec / DuckDB
- Integrations: example client / simple agent demo

### Long term
- Ecosystem: exporters (SDKs), adapters for common docs stacks (mkdocs, swagger), and production deployment patterns

## Suggested Tech Stack (provisional)

- Runtime: Python 3.11+, FastAPI, Pydantic v2
- Parsing: tree-sitter, openapi-parser, markdown pipeline
- Storage & search: SQLite + sqlite-vec / DuckDB
- Protocol: official MCP SDK for Python
- Tokenization: tiktoken

## How to contribute

- Read the spec (this repo) and comment on open design questions
- Prototype ingestion for one source type (OpenAPI or Markdown)
- Implement a test for token-efficiency and schema preservation
- Open issues and PRs for small, incremental improvements — start with tests/examples

## Next steps I can take for you

- Shorten or expand the README for a specific audience (developer vs product)
- Extract a one‑page API for `/llms.txt` and a sample `/llms-small.txt`
- Create an initial project skeleton (FastAPI MCP server + sample ingestion) and open a PR (I will ask you to confirm repo/branch before making changes)
- Convert parts of your spec into executable test cases (token benchmarks, MCP conformance)

## License & Contact

Add your chosen license file (e.g., LICENSE.md) and maintainers/contact info here.
