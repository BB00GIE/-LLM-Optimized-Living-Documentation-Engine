from __future__ import annotations

import argparse
import json
import sys
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
    build.add_argument("--python", action="append", type=Path, default=[], help="Python source file or directory")
    build.add_argument("--typescript", action="append", type=Path, default=[], help="TypeScript source file or directory")
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

    benchmark = commands.add_parser("benchmark", help="Run token efficiency benchmarks comparing raw vs optimized docs")
    benchmark.add_argument("--html", type=Path, default=None, help="Custom HTML web docs file to benchmark")
    benchmark.add_argument("--spec", type=Path, default=None, help="Custom OpenAPI spec file (JSON or YAML) to benchmark")
    benchmark.add_argument("--tokenizer", default="cl100k_base", choices=["cl100k_base", "o200k_base"], help="Tokenizer encoding")

    eval_cmd = commands.add_parser("eval", help="Run E2E agent evaluation scenarios against the living documentation engine")
    eval_cmd.add_argument("--openapi", type=Path, default=Path("examples/openapi.yaml"), help="OpenAPI spec path")
    eval_cmd.add_argument("--python", type=Path, default=Path("examples/src/client.py"), help="Python source path")
    eval_cmd.add_argument("--typescript", type=Path, default=Path("examples/src/types.ts"), help="TypeScript source path")
    eval_cmd.add_argument("--output", type=Path, default=Path("build/eval"), help="Output directory for index artifacts")
    eval_cmd.add_argument("--tokenizer", default="cl100k_base", choices=["cl100k_base", "o200k_base"], help="Tokenizer encoding")

    conformance_cmd = commands.add_parser("conformance", help="Run automated MCP protocol conformance test suite")
    conformance_cmd.add_argument("--index", type=Path, default=Path("build/docs-index.json"), help="Path to docs-index.json")

    verify_cmd = commands.add_parser("verify", help="Execute complete 4-step real-world verification suite with database analytics")
    verify_cmd.add_argument("--spec", type=Path, default=Path("examples/posthog_production_spec.yaml"), help="OpenAPI spec path")
    verify_cmd.add_argument("--output", type=Path, default=Path("verification_results"), help="Results directory")

    args = parser.parse_args()
    if args.command == "build":
        manifest = build_artifacts(
            output_directory=args.output,
            openapi_files=args.openapi,
            markdown_directories=args.markdown,
            python_sources=args.python,
            typescript_sources=args.typescript,
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
    elif args.command == "benchmark":
        from living_docs.benchmark import run_token_efficiency_benchmark

        results = run_token_efficiency_benchmark(
            custom_html_path=args.html,
            custom_openapi_path=args.spec,
            encoding_name=args.tokenizer,
        )
        print("\n=== Token Efficiency Benchmark Results ===")
        for r in results:
            print(f"\nScenario: {r.scenario}")
            print(f"  Raw Documentation:        {r.raw_tokens} tokens")
            print(f"  Living Docs Output:       {r.optimized_tokens} tokens")
            print(f"  Tokens Saved:             {r.tokens_saved} tokens")
            print(f"  Token Reduction:          {r.reduction_percentage:.1f}%")
            print(f"  Complete Schema Verified: {'YES' if r.schema_preserved else 'NO'}")
        print("\n==========================================\n")
    elif args.command == "eval":
        from living_docs.eval_harness import evaluate_living_docs_engine

        report = evaluate_living_docs_engine(
            output_dir=args.output,
            openapi_path=args.openapi,
            python_src_path=args.python if args.python.exists() else None,
            typescript_src_path=args.typescript if args.typescript.exists() else None,
            encoding_name=args.tokenizer,
        )
        print("\n=== Living Docs Agent Evaluation Report ===")
        print(f"Total Tasks:          {report.total_tasks}")
        print(f"Passed Tasks:         {report.passed_tasks}")
        print(f"First-Pass Accuracy:  {report.first_pass_accuracy:.1f}%")
        print(f"Tokens Consumed:      {report.total_tokens_consumed} tokens")
        for r in report.results:
            status_str = "PASS" if r.passed else "FAIL"
            print(f"  [{status_str}] {r.task_id}: {r.description} ({r.tokens_consumed} tokens)")
            for err in r.errors:
                print(f"         Error: {err}")
        print("\n===========================================\n")
        if report.first_pass_accuracy < 90.0:
            sys.exit(1)
    elif args.command == "conformance":
        import asyncio
        from living_docs.conformance import run_mcp_conformance_suite

        if not args.index.exists():
            print("Building temporary index at build/docs-index.json...")
            build_artifacts(
                output_directory=args.index.parent,
                openapi_files=[Path("examples/openapi.yaml")],
            )

        report = asyncio.run(run_mcp_conformance_suite(args.index))
        print("\n=== MCP Protocol Conformance Report ===")
        print(f"Checks Passed: {report.passed_checks} / {report.total_checks}")
        print(f"Status:        {'CONFORMANT' if report.all_passed else 'NON-CONFORMANT'}")
        for c in report.checks:
            mark = "PASS" if c.passed else "FAIL"
            print(f"  [{mark}] {c.name}: {c.message}")
        print("\n=======================================\n")
        if not report.all_passed:
            sys.exit(1)
    elif args.command == "verify":
        from living_docs.verification_suite import run_full_verification

        summary = run_full_verification(results_dir=args.output, spec_path=args.spec)
        print("\n=== Real-World Verification & Data Analytics Summary ===")
        print(f"Total Experiments:      {summary['total_experiments']}")
        print(f"Passed Experiments:     {summary['passed_experiments']}")
        print(f"Overall Success Rate:   {summary['overall_success_rate']:.1f}%")
        print("\nToken Reduction Statistics:")
        print(f"  Mean Token Reduction: {summary['token_reduction_stats']['mean_pct']:.1f}%")
        print(f"  Median Reduction:     {summary['token_reduction_stats']['median_pct']:.1f}%")
        print(f"  Range:                {summary['token_reduction_stats']['min_pct']:.1f}% - {summary['token_reduction_stats']['max_pct']:.1f}%")
        print(f"  Total Tokens Saved:   {summary['token_reduction_stats']['total_tokens_saved']:,} tokens")
        print("\nLatency Metrics (ms):")
        print(f"  P50 Latency:          {summary['latency_stats_ms']['p50']:.2f} ms")
        print(f"  P95 Latency:          {summary['latency_stats_ms']['p95']:.2f} ms")
        print(f"  P99 Latency:          {summary['latency_stats_ms']['p99']:.2f} ms")
        print("\nArtifacts & Data Stores Generated:")
        print(f"  SQLite Database:      {summary['database_file']}")
        print(f"  CSV Metrics Log:      {summary['csv_file']}")
        print(f"  JSON Full Dump:       {summary['json_file']}")
        print("========================================================\n")


if __name__ == "__main__":
    main()
