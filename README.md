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
- TypeScript AST extraction for `interface`, `type`, `enum`, `function`, and `const` arrow function declarations with JSDoc
- Static artifacts generation (`/llms.txt`, `/llms-small.txt`, `/llms-full.txt`)
- Hybrid search (BM25 + Dense Vectors) with Reciprocal Rank Fusion
- Multi-tokenizer support (`cl100k_base` and `o200k_base`)
- Dual MCP server transports: stdio and SSE (HTTP) with manifest, search, and exact API lookup
- Automated Token Efficiency Benchmark suite (>60% reduction target proven, achieving 61%–92%)
- E2E Agent Evaluation Harness verifying zero invalid field errors and first-pass accuracy
- Automated MCP Protocol Conformance Test Suite (validating resources, tools, error contracts)

### Long term
- Ecosystem: exporters (SDKs), adapters for common docs stacks (mkdocs, swagger), and production deployment patterns

## Suggested Tech Stack

- Runtime: Python 3.11+ and the official MCP SDK
- Parsing: PyYAML for OpenAPI YAML, Python `ast`, TypeScript regex/AST parser, built-in JSON/MDX processing
- Storage & search: SQLite FTS5 (BM25) + embedded vector similarity
- Protocol: official MCP SDK for Python (`stdio` and `sse` transports with Starlette/Uvicorn)
- Tokenization: tiktoken (`cl100k_base` and `o200k_base`)

## Testing & Verification

To verify that the living documentation engine achieves its architectural promises in real-world agentic workflows, the system undergoes a 4-step empirical verification suite alongside automated tests:

### Step 1: Ingesting a Real-World Production API
- **Goal:** Prove that the ingestion pipeline processes complex, multi-thousand-line production OpenAPI specifications with deep reference structures.
- **Method:**
  1. Download an official production OpenAPI spec (e.g. PostHog, Stripe, or GitHub REST API).
  2. Execute `living-docs build`:
     ```powershell
     living-docs build --openapi production_spec.yaml --output build/
     ```
  3. Verify that all `$ref` pointers resolve into self-contained contracts and inspect `/llms.txt`, `/llms-small.txt`, and `/llms-full.txt`.

### Step 2: Head-to-Head Token Benchmark on Live Docs
- **Goal:** Quantify and prove the **>60% to 90% token reduction** claim against live human documentation.
- **Method:**
  1. Measure full token weight of a human-targeted web documentation page (including layout wrappers, navigation trees, scripts, styling, and conversational prose).
  2. Run the token efficiency benchmark tool:
     ```powershell
     living-docs benchmark --html sample_page.html --spec sample_spec.json
     ```
  3. Verify that the living docs schema output preserves 100% of required fields, types, and constraints while reducing total context token count by over 70%–92%.

### Step 3: Live MCP Integration with AI Agents (Cursor / Claude Desktop / Custom Agents)
- **Goal:** Prove that autonomous coding agents interactively discover, query, and call APIs with zero visual overhead.
- **Method:**
  1. Launch the MCP server over stdio or SSE:
     ```powershell
     living-docs serve --index build/docs-index.json --transport stdio
     ```
  2. Register the living-docs server in your client configuration (e.g. `.cursor/mcp.json` or Claude Desktop config).
  3. Prompt the agent with an end-to-end integration task:
     > *"Query the living docs MCP server to find how to create a batch event in the API, and write a runnable Python script to execute it."*
  4. Verify that the agent queries `docs://manifest`, calls `get_api_spec`, and generates syntactically valid code on the first attempt without hallucinating parameter names.

### Step 4: Robustness & Adversarial Chaos Testing
- **Goal:** Ensure the engine survives adversarial agent inputs, non-existent routes, and high-concurrency workloads.
- **Method:**
  1. **Hallucinated Route Handling:** Request non-existent endpoints (e.g. `/api/v1/invalid_route`). Assert that the engine returns structured `RESOURCE_NOT_FOUND` responses with valid close-match path suggestions.
  2. **Multi-Threaded Concurrency:** Dispatch 50+ parallel tool requests across concurrent worker threads to the SSE endpoint to verify zero SQLite deadlocks or connection drops.
  3. **Strict Token Ceiling Enforcement:** Invoke `search_docs` under strict budgets (`max_tokens=200`, `500`, `1000`) and verify via `tiktoken` that no returned payload exceeds the budget.

---

### Automated Verification Commands

- **Run Token Efficiency Benchmark**:
  ```powershell
  living-docs benchmark
  ```
  Measures token savings of Living Docs outputs against human HTML documentation (>90% reduction) and raw OpenAPI specs (>60% reduction).

- **Run Agent Evaluation Harness**:
  ```powershell
  living-docs eval
  ```
  Tests E2E task execution accuracy and schema conformance across REST contracts, error guidance, and code signatures.

- **Run MCP Protocol Conformance**:
  ```powershell
  living-docs conformance
  ```
  Validates resource URI formats, MIME types, tool schemas, and structured error boundaries.

- **Run Full Automated Test Suite**:
  ```powershell
  python -m pytest -v
  ```

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
