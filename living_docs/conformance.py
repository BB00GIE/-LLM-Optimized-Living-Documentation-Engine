from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@dataclass
class ConformanceCheck:
    name: str
    passed: bool
    message: str


@dataclass
class ConformanceReport:
    total_checks: int
    passed_checks: int
    all_passed: bool
    checks: list[ConformanceCheck]


async def run_mcp_conformance_suite(index_path: Path) -> ConformanceReport:
    """Verify MCP protocol conformance across resources, tools, and error contracts."""
    checks: list[ConformanceCheck] = []

    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "living_docs", "serve", "--index", str(index_path)],
    )

    try:
        async with stdio_client(parameters) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()

                # 1. Resource List Conformance
                resources_result = await session.list_resources()
                resource_uris = [str(r.uri) for r in resources_result.resources]
                manifest_present = "docs://manifest" in resource_uris
                checks.append(ConformanceCheck(
                    name="resource_registration_docs_manifest",
                    passed=manifest_present,
                    message="Resource docs://manifest is registered" if manifest_present else f"docs://manifest missing from {resource_uris}",
                ))

                # 2. Resource Read Conformance & JSON Schema
                manifest_data = await session.read_resource("docs://manifest")
                manifest_text = manifest_data.contents[0].text
                try:
                    manifest_json = json.loads(manifest_text)
                    valid_manifest = "version" in manifest_json and "sections" in manifest_json and "total_tokens" in manifest_json
                    checks.append(ConformanceCheck(
                        name="resource_read_manifest_schema",
                        passed=valid_manifest,
                        message="docs://manifest returns valid structured JSON" if valid_manifest else "docs://manifest missing required keys",
                    ))
                except json.JSONDecodeError as e:
                    checks.append(ConformanceCheck(
                        name="resource_read_manifest_schema",
                        passed=False,
                        message=f"docs://manifest is not valid JSON: {e}",
                    ))

                # 3. Tool List Conformance
                tools_result = await session.list_tools()
                tool_names = {t.name for t in tools_result.tools}
                expected_tools = {"search_docs", "get_api_spec"}
                tools_present = expected_tools.issubset(tool_names)
                checks.append(ConformanceCheck(
                    name="tools_registration_conformance",
                    passed=tools_present,
                    message=f"Tools registered: {tool_names}" if tools_present else f"Expected {expected_tools}, got {tool_names}",
                ))

                # 4. Tool Execution: get_api_spec valid operation
                api_res = await session.call_tool("get_api_spec", {"endpoint_path": "/api/tasks", "method": "POST"})
                api_data = json.loads(api_res.content[0].text)
                api_ok = api_res.isError is False and api_data.get("status") == "ok" and "spec" in api_data
                checks.append(ConformanceCheck(
                    name="tool_call_get_api_spec_success",
                    passed=api_ok,
                    message="get_api_spec returns status ok with schema" if api_ok else f"get_api_spec failed: {api_data}",
                ))

                # 5. Tool Error Contract: get_api_spec non-existent operation
                err_res = await session.call_tool("get_api_spec", {"endpoint_path": "/api/nonexistent", "method": "GET"})
                err_data = json.loads(err_res.content[0].text)
                err_ok = err_data.get("status") == "error" and err_data.get("error_code") == "RESOURCE_NOT_FOUND" and "context" in err_data
                checks.append(ConformanceCheck(
                    name="tool_call_error_contract_conformance",
                    passed=err_ok,
                    message="get_api_spec returns structured RESOURCE_NOT_FOUND contract" if err_ok else f"Invalid error contract: {err_data}",
                ))

                # 6. Tool Execution: search_docs strict token ceiling
                max_tok = 200
                search_res = await session.call_tool("search_docs", {"query": "tasks", "max_tokens": max_tok})
                search_data = json.loads(search_res.content[0].text)
                search_ok = search_res.isError is False and "results" in search_data and search_data.get("token_count", 9999) <= max_tok
                checks.append(ConformanceCheck(
                    name="tool_call_search_docs_token_budget",
                    passed=search_ok,
                    message=f"search_docs payload ({search_data.get('token_count')} tokens) strictly within budget ({max_tok})" if search_ok else f"Budget exceeded: {search_data}",
                ))
    except Exception as exc:
        checks.append(ConformanceCheck(
            name="mcp_server_connection",
            passed=False,
            message=f"Failed to connect or initialize MCP server: {exc}",
        ))

    passed_count = sum(1 for c in checks if c.passed)
    return ConformanceReport(
        total_checks=len(checks),
        passed_checks=passed_count,
        all_passed=passed_count == len(checks),
        checks=checks,
    )
