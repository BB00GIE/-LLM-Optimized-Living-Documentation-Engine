from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Literal

from living_docs.engine import DocumentationEngine, build_artifacts


def _run_mcp(index_path: Path) -> None:
    from mcp.server.fastmcp import FastMCP

    engine = DocumentationEngine.from_index(index_path)
    server = FastMCP("Living Documentation Engine")

    @server.resource("docs://manifest", mime_type="application/json")
    def manifest() -> str:
        return json.dumps(engine.manifest, ensure_ascii=False)

    @server.tool()
    def search_docs(query: str, max_tokens: int = 2000) -> str:
        """Search documentation with BM25 ranking and a strict token budget."""
        result = engine.search_docs(query, max_tokens)
        return json.dumps(result, ensure_ascii=False, separators=(",", ":"))

    @server.tool()
    def get_api_spec(endpoint_path: str, method: Literal["GET", "POST", "PUT", "DELETE", "PATCH"]) -> dict:
        """Return the complete schema-first documentation for an exact API operation."""
        return engine.get_api_spec(endpoint_path, method)

    server.run(transport="stdio")


def main() -> None:
    parser = argparse.ArgumentParser(prog="living-docs")
    commands = parser.add_subparsers(dest="command", required=True)

    build = commands.add_parser("build", help="Build static artifacts and the MCP search index")
    build.add_argument("--openapi", action="append", type=Path, default=[], help="OpenAPI 3.x JSON/YAML file")
    build.add_argument("--markdown", action="append", type=Path, default=[], help="Markdown/MDX source directory")
    build.add_argument("--output", type=Path, required=True, help="Output directory")
    build.add_argument("--project-name", default="Documentation")
    build.add_argument("--small-token-budget", type=int, default=4000)

    serve = commands.add_parser("serve", help="Run the MCP server over stdio")
    serve.add_argument("--index", type=Path, required=True, help="Path to docs-index.json")

    args = parser.parse_args()
    if args.command == "build":
        manifest = build_artifacts(
            output_directory=args.output,
            openapi_files=args.openapi,
            markdown_directories=args.markdown,
            project_name=args.project_name,
            small_token_budget=args.small_token_budget,
        )
        print(f"Built {len(manifest['sections'])} sections ({manifest['total_tokens']} tokens) in {args.output}")
    elif args.command == "serve":
        _run_mcp(args.index)


if __name__ == "__main__":
    main()
