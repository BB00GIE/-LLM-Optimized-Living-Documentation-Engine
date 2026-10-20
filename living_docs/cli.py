from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Literal

from living_docs.engine import DocumentationEngine, build_artifacts


def create_mcp_server(
    index_path: Path,
    host: str = "127.0.0.1",
    port: int = 8000,
    encoding_name: str = "cl100k_base",
):
    from mcp.server.fastmcp import FastMCP

    engine = DocumentationEngine.from_index(index_path, encoding_name=encoding_name)
    server = FastMCP("Living Documentation Engine", host=host, port=port)

    @server.resource("docs://manifest", mime_type="application/json")
    def manifest() -> str:
        return json.dumps(engine.manifest, ensure_ascii=False)

    @server.tool()
    def search_docs(query: str, max_tokens: int = 2000) -> str:
        """Search documentation with hybrid BM25 + dense vector ranking and a strict token budget."""
        result = engine.search_docs(query, max_tokens)
        return json.dumps(result, ensure_ascii=False, separators=(",", ":"))

    @server.tool()
    def get_api_spec(endpoint_path: str, method: Literal["GET", "POST", "PUT", "DELETE", "PATCH"]) -> dict:
        """Return the complete schema-first documentation for an exact API operation."""
        return engine.get_api_spec(endpoint_path, method)

    return server, engine


def _run_mcp(
    index_path: Path,
    transport: Literal["stdio", "sse"] = "stdio",
    host: str = "127.0.0.1",
    port: int = 8000,
    encoding_name: str = "cl100k_base",
) -> None:
    server, _ = create_mcp_server(index_path, host=host, port=port, encoding_name=encoding_name)
    server.run(transport=transport)


def main() -> None:
    parser = argparse.ArgumentParser(prog="living-docs")
    commands = parser.add_subparsers(dest="command", required=True)

    build = commands.add_parser("build", help="Build static artifacts and the MCP search index")
    build.add_argument("--openapi", action="append", type=Path, default=[], help="OpenAPI 3.x JSON/YAML file")
    build.add_argument("--markdown", action="append", type=Path, default=[], help="Markdown/MDX source directory")
    build.add_argument("--output", type=Path, required=True, help="Output directory")
    build.add_argument("--project-name", default="Documentation")
    build.add_argument("--small-token-budget", type=int, default=4000)
    build.add_argument("--tokenizer", default="cl100k_base", choices=["cl100k_base", "o200k_base"], help="Tokenizer encoding")

    serve = commands.add_parser("serve", help="Run the MCP server over stdio or SSE")
    serve.add_argument("--index", type=Path, required=True, help="Path to docs-index.json")
    serve.add_argument("--transport", default="stdio", choices=["stdio", "sse"], help="MCP transport protocol")
    serve.add_argument("--host", default="127.0.0.1", help="Host interface for SSE server")
    serve.add_argument("--port", type=int, default=8000, help="Port for SSE server")
    serve.add_argument("--tokenizer", default="cl100k_base", choices=["cl100k_base", "o200k_base"], help="Tokenizer encoding")

    args = parser.parse_args()
    if args.command == "build":
        manifest = build_artifacts(
            output_directory=args.output,
            openapi_files=args.openapi,
            markdown_directories=args.markdown,
            project_name=args.project_name,
            small_token_budget=args.small_token_budget,
            encoding_name=args.tokenizer,
        )
        print(f"Built {len(manifest['sections'])} sections ({manifest['total_tokens']} tokens) in {args.output}")
    elif args.command == "serve":
        _run_mcp(
            args.index,
            transport=args.transport,
            host=args.host,
            port=args.port,
            encoding_name=args.tokenizer,
        )


if __name__ == "__main__":
    main()
