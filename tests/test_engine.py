import asyncio
import json
import sys
from pathlib import Path

from living_docs.engine import DocumentationEngine, _clean_markdown, build_artifacts, count_tokens


def test_builds_static_artifacts_and_resolves_schema_refs(tmp_path):
    output = tmp_path / "out"
    manifest = build_artifacts(
        output_directory=output,
        openapi_files=[Path("examples/openapi.yaml")],
        markdown_directories=[Path("examples/docs")],
        project_name="Example",
        small_token_budget=200,
    )

    assert len(manifest["sections"]) == 4
    assert {path.name for path in output.iterdir()} == {
        "docs-index.json", "llms.txt", "llms-small.txt", "llms-full.txt"
    }
    full = (output / "llms-full.txt").read_text(encoding="utf-8")
    assert '"required":["id","title"]' in full
    assert "import { Callout }" not in full
    assert "The `title` field is required." in full
    assert count_tokens((output / "llms-small.txt").read_text(encoding="utf-8")) <= 200


def test_markdown_cleanup_preserves_fenced_examples_and_strips_layout_noise():
    source = """---
title: Example
---
import Layout from "./layout";
<Callout>Keep this guidance.</Callout>
<script>discard this script</script>

```html
<script>keep this example</script>
<a href="./relative">keep this code</a>
```

[Read more](./details.md)
Contact <https://example.com>.
"""
    result = _clean_markdown(source)

    assert "discard this script" not in result
    assert "<script>keep this example</script>" in result
    assert '<a href="./relative">keep this code</a>' in result
    assert "Keep this guidance." in result
    assert "Read more" in result
    assert "./details.md" not in result
    assert "<https://example.com>" in result


def test_mcp_operations_are_exact_and_search_respects_full_payload_budget(tmp_path):
    output = tmp_path / "out"
    build_artifacts(
        output_directory=output,
        openapi_files=[Path("examples/openapi.yaml")],
    )
    engine = DocumentationEngine.from_index(output / "docs-index.json")

    exact = engine.get_api_spec("/api/tasks", "post")
    assert exact["status"] == "ok"
    assert '"required":["title"]' in exact["spec"]
    path_parameter = engine.get_api_spec("/api/tasks/{task_id}", "GET")
    assert "`task_id` (path, required)" in path_parameter["spec"]

    missing = engine.get_api_spec("/api/task", "GET")
    assert missing["error_code"] == "RESOURCE_NOT_FOUND"
    assert "/api/tasks" in missing["context"]["suggested_paths"]

    result = engine.search_docs("tasks", max_tokens=256)
    assert result["results"]
    assert result["token_count"] <= 256
    assert result["token_count"] == count_tokens(
        json.dumps(result, ensure_ascii=False, separators=(",", ":"))
    )


def test_mcp_stdio_exposes_manifest_and_tools(tmp_path):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    output = tmp_path / "out"
    build_artifacts(output, openapi_files=[Path("examples/openapi.yaml")])

    async def exercise_server():
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "living_docs", "serve", "--index", str(output / "docs-index.json")],
        )
        async with stdio_client(parameters) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                resources = await session.list_resources()
                tools = await session.list_tools()
                manifest = await session.read_resource("docs://manifest")
                result = await session.call_tool(
                    "get_api_spec",
                    {"endpoint_path": "/api/tasks", "method": "POST"},
                )
                search = await session.call_tool("search_docs", {"query": "tasks", "max_tokens": 256})
                assert any(str(resource.uri) == "docs://manifest" for resource in resources.resources)
                assert {tool.name for tool in tools.tools} == {"search_docs", "get_api_spec"}
                assert json.loads(manifest.contents[0].text)["project"] == "Documentation"
                assert manifest.contents[0].mimeType == "application/json"
                assert result.isError is False
                assert json.loads(result.content[0].text)["status"] == "ok"
                search_payload = json.loads(search.content[0].text)
                assert search_payload["token_count"] <= 256
                assert search_payload["token_count"] == count_tokens(search.content[0].text)

    asyncio.run(exercise_server())
