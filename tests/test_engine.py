import asyncio
import json
import math
import sys
import threading
from pathlib import Path

import uvicorn
from living_docs.cli import create_mcp_server
from living_docs.embeddings import HashingEmbedder, cosine_similarity, pack_vector
from living_docs.engine import (
    DocumentationEngine,
    _clean_markdown,
    build_artifacts,
    count_tokens,
)


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


def test_search_docs_input_validation_boundaries(tmp_path):
    output = tmp_path / "out"
    build_artifacts(
        output_directory=output,
        openapi_files=[Path("examples/openapi.yaml")],
    )
    engine = DocumentationEngine.from_index(output / "docs-index.json")

    empty_res = engine.search_docs("   ")
    assert empty_res["error_code"] == "INVALID_QUERY"

    long_res = engine.search_docs("a" * 2001)
    assert long_res["error_code"] == "INVALID_QUERY"
    assert "2000" in long_res["message"]

    low_tokens = engine.search_docs("tasks", max_tokens=10)
    assert low_tokens["error_code"] == "INVALID_TOKEN_BUDGET"

    high_tokens = engine.search_docs("tasks", max_tokens=50000)
    assert high_tokens["error_code"] == "INVALID_TOKEN_BUDGET"


def test_embeddings_and_vector_similarity():
    embedder = HashingEmbedder(dimension=128)
    vec1 = embedder.embed("create a task in the system")
    vec2 = embedder.embed("creating new tasks")
    vec3 = embedder.embed("astronomy planets cosmic observatory")

    norm1 = math.sqrt(sum(v * v for v in vec1))
    assert abs(norm1 - 1.0) < 1e-4

    b1 = pack_vector(vec1)
    b2 = pack_vector(vec2)
    b3 = pack_vector(vec3)

    sim_self = cosine_similarity(b1, b1)
    sim_related = cosine_similarity(b1, b2)
    sim_unrelated = cosine_similarity(b1, b3)

    assert abs(sim_self - 1.0) < 1e-4
    assert sim_related > sim_unrelated


def test_hybrid_search_rrf_scoring(tmp_path):
    output = tmp_path / "out"
    build_artifacts(
        output_directory=output,
        openapi_files=[Path("examples/openapi.yaml")],
        markdown_directories=[Path("examples/docs")],
    )
    engine = DocumentationEngine.from_index(output / "docs-index.json")

    # Search with hybrid weights
    hybrid_res = engine.search_docs("quickstart create", max_tokens=1000, bm25_weight=0.5, vector_weight=0.5)
    assert hybrid_res["results"]
    top_doc = hybrid_res["results"][0]
    assert "quickstart" in top_doc["id"] or "tasks" in top_doc["id"]


def test_multi_tokenizer_o200k(tmp_path):
    output = tmp_path / "out_o200k"
    manifest = build_artifacts(
        output_directory=output,
        openapi_files=[Path("examples/openapi.yaml")],
        markdown_directories=[Path("examples/docs")],
        encoding_name="o200k_base",
    )
    assert manifest["total_tokens"] > 0
    engine = DocumentationEngine.from_index(output / "docs-index.json")
    assert engine.encoding_name == "o200k_base"
    res = engine.search_docs("tasks", max_tokens=300)
    assert res["results"]
    assert res["token_count"] == count_tokens(
        json.dumps(res, ensure_ascii=False, separators=(",", ":")),
        encoding_name="o200k_base",
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


def test_mcp_sse_transport_exposes_tools_and_manifest(tmp_path):
    from mcp import ClientSession
    from mcp.client.sse import sse_client

    output = tmp_path / "out_sse"
    build_artifacts(output, openapi_files=[Path("examples/openapi.yaml")])

    port = 8991
    server, _ = create_mcp_server(output / "docs-index.json", host="127.0.0.1", port=port)
    config = uvicorn.Config(server.sse_app(), host="127.0.0.1", port=port, log_level="error")
    uv_server = uvicorn.Server(config)
    thread = threading.Thread(target=uv_server.run, daemon=True)
    thread.start()

    async def exercise_sse():
        await asyncio.sleep(0.5)
        async with sse_client(f"http://127.0.0.1:{port}/sse") as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tools = await session.list_tools()
                assert {tool.name for tool in tools.tools} == {"search_docs", "get_api_spec"}
                res = await session.call_tool("get_api_spec", {"endpoint_path": "/api/tasks", "method": "GET"})
                assert json.loads(res.content[0].text)["status"] == "ok"

    try:
        asyncio.run(exercise_sse())
    finally:
        uv_server.should_exit = True
