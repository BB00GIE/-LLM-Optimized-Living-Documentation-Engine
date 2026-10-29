import asyncio
import json
import math
import sys
import threading
from pathlib import Path

import uvicorn
from living_docs.ast_parser import extract_python_sections, extract_typescript_sections
from living_docs.cli import create_mcp_server
from living_docs.embeddings import HashingEmbedder, cosine_similarity, pack_vector
from living_docs.engine import (
    DocumentationEngine,
    _clean_markdown,
    _resolve_local_refs,
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


def test_openapi_ref_recursion_depth_guard():
    # Construct a chained schema with 70 levels of local references
    doc: dict = {"components": {"schemas": {}}}
    for i in range(70):
        doc["components"]["schemas"][f"Node{i}"] = {
            "$ref": f"#/components/schemas/Node{i+1}"
        }
    doc["components"]["schemas"]["Node70"] = {"type": "string"}

    import pytest

    with pytest.raises(ValueError, match="recursion depth"):
        _resolve_local_refs({"$ref": "#/components/schemas/Node0"}, doc)


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
Use `List<string>` and Map<string, int> for collections.
"""
    result = _clean_markdown(source)

    assert "discard this script" not in result
    assert "<script>keep this example</script>" in result
    assert '<a href="./relative">keep this code</a>' in result
    assert "Keep this guidance." in result
    assert "Read more" in result
    assert "./details.md" not in result
    assert "<https://example.com>" in result
    assert "`List<string>`" in result
    assert "Map<string, int>" in result


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

    # Trailing slash normalization
    with_slash = engine.get_api_spec("/api/tasks/", "post")
    assert with_slash["status"] == "ok"
    assert '"required":["title"]' in with_slash["spec"]

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

    none_res = engine.search_docs(None)  # type: ignore
    assert none_res["error_code"] == "INVALID_QUERY"

    long_res = engine.search_docs("a" * 2001)
    assert long_res["error_code"] == "INVALID_QUERY"
    assert "2000" in long_res["message"]

    low_tokens = engine.search_docs("tasks", max_tokens=10)
    assert low_tokens["error_code"] == "INVALID_TOKEN_BUDGET"

    high_tokens = engine.search_docs("tasks", max_tokens=50000)
    assert high_tokens["error_code"] == "INVALID_TOKEN_BUDGET"

    # get_api_spec defensive type checking
    none_path = engine.get_api_spec(None, "GET")  # type: ignore
    assert none_path["error_code"] == "INVALID_PATH"

    none_method = engine.get_api_spec("/api/tasks", None)  # type: ignore
    assert none_method["error_code"] == "INVALID_METHOD"


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


def test_precomputed_vectors_persisted_in_index(tmp_path):
    output = tmp_path / "out_vectors"
    build_artifacts(
        output_directory=output,
        openapi_files=[Path("examples/openapi.yaml")],
        markdown_directories=[Path("examples/docs")],
    )
    index_data = json.loads((output / "docs-index.json").read_text(encoding="utf-8"))
    assert "vectors" in index_data
    assert len(index_data["vectors"]) == len(index_data["sections"])

    # Initializing from index should load vectors directly without needing an embedder to compute them
    class FailingEmbedder:
        dimension = 128
        def embed(self, text: str):
            raise AssertionError("embed should not be called when precomputed vectors are available")
        def embed_batch(self, texts):
            raise AssertionError("embed_batch should not be called")

    engine = DocumentationEngine.from_index(output / "docs-index.json", embedder=FailingEmbedder())
    # Should successfully search with query embedding
    FailingEmbedder.embed = lambda self, text: [0.1] * 128
    res = engine.search_docs("quickstart", max_tokens=500)
    assert res["results"]


def test_concurrent_multithreaded_search(tmp_path):
    import concurrent.futures

    output = tmp_path / "out_threads"
    build_artifacts(output, openapi_files=[Path("examples/openapi.yaml")])
    engine = DocumentationEngine.from_index(output / "docs-index.json")

    def run_search(query: str):
        return engine.search_docs(query, max_tokens=500)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        queries = ["tasks", "create", "api", "limit", "task_id"] * 5
        results = list(executor.map(run_search, queries))

    assert len(results) == 25
    assert all("results" in r for r in results)


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
    import socket
    import time
    from mcp import ClientSession
    from mcp.client.sse import sse_client

    output = tmp_path / "out_sse"
    build_artifacts(output, openapi_files=[Path("examples/openapi.yaml")])

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    server, _ = create_mcp_server(output / "docs-index.json", host="127.0.0.1", port=port)
    config = uvicorn.Config(server.sse_app(), host="127.0.0.1", port=port, log_level="error")
    uv_server = uvicorn.Server(config)
    thread = threading.Thread(target=uv_server.run, daemon=True)
    thread.start()

    async def exercise_sse():
        deadline = time.time() + 5.0
        connected = False
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                    connected = True
                    break
            except OSError:
                await asyncio.sleep(0.02)
        assert connected, "SSE server failed to start within 5.0s"

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
        thread.join(timeout=3.0)


def test_extract_python_ast_sections(tmp_path):
    sections = extract_python_sections([Path("examples/src/client.py")])
    names = {s.title for s in sections}
    assert "class TaskRecord" in names
    assert "class TaskClient" in names
    assert "def format_task_summary" in names

    client_sec = next(s for s in sections if s.title == "class TaskClient")
    assert "def create_task(title: str, completed: bool = False) -> TaskRecord" in client_sec.content
    assert "def get_task(task_id: str) -> Optional[TaskRecord]" in client_sec.content
    assert "Client for managing tasks" in client_sec.description

    # Positional-only parameter support
    posonly_file = tmp_path / "posonly.py"
    posonly_file.write_text(
        "def query(sql: str, /, limit: int = 100) -> list[dict]:\n    '''Run raw query.'''\n    return []\n",
        encoding="utf-8",
    )
    pos_sec = extract_python_sections([posonly_file])
    assert "def query(sql: str, /, limit: int = 100) -> list[dict]" in pos_sec[0].content

    # Unreadable or invalid encoding should be skipped gracefully
    bad_file = tmp_path / "bad.py"
    bad_file.write_bytes(b"\xff\xfe\x00\x00invalid")
    assert extract_python_sections([bad_file]) == []

    # Private methods (starting with _) should be excluded, except __init__
    priv_file = tmp_path / "private_methods.py"
    priv_file.write_text(
        "class Service:\n    def __init__(self, key: str): pass\n    def public_api(self): pass\n    def _private_worker(self): pass\n",
        encoding="utf-8",
    )
    priv_sec = extract_python_sections([priv_file])
    assert "__init__" in priv_sec[0].content
    assert "public_api" in priv_sec[0].content
    assert "_private_worker" not in priv_sec[0].content


def test_extract_typescript_ast_sections(tmp_path):
    sections = extract_typescript_sections([Path("examples/src/types.ts")])
    names = {s.title for s in sections}
    assert "type TaskPriority" in names
    assert "enum TaskStatus" in names
    assert "interface TaskItem" in names
    assert "interface CreateTaskInput" in names
    assert "async function listTasks" in names
    assert "const fetchTaskById" in names

    list_sec = next(s for s in sections if s.title == "async function listTasks")
    assert "Promise<TaskItem[]>" in list_sec.content
    assert "Fetch tasks filtered by completion status" in list_sec.description

    const_sec = next(s for s in sections if s.title == "const fetchTaskById")
    assert "async (id: string): Promise<TaskItem | null>" in const_sec.content

    # Nested braces in TypeScript interface should not be truncated
    nested_file = tmp_path / "nested.ts"
    nested_file.write_text(
        "export interface DeepConfig {\n  nested: {\n    key: string;\n    count: number;\n  };\n  active: boolean;\n}\n",
        encoding="utf-8",
    )
    nested_secs = extract_typescript_sections([nested_file])
    assert "active: boolean;" in nested_secs[0].content
    assert "count: number;" in nested_secs[0].content


def test_builds_artifacts_with_code_sources(tmp_path):
    output = tmp_path / "out_code"
    manifest = build_artifacts(
        output_directory=output,
        openapi_files=[Path("examples/openapi.yaml")],
        markdown_directories=[Path("examples/docs")],
        python_sources=[Path("examples/src/client.py")],
        typescript_sources=[Path("examples/src/types.ts")],
        project_name="Full Tasks System",
    )

    # 4 (OpenAPI) + 1 (Markdown) + 3 (Python: 2 classes, 1 func) + 4 (TS: 1 type, 2 interfaces, 1 func) = 12 sections
    assert len(manifest["sections"]) >= 10
    engine = DocumentationEngine.from_index(output / "docs-index.json")

    # Search for python method
    py_res = engine.search_docs("create_task TaskClient", max_tokens=500)
    assert py_res["results"]
    assert any("TaskClient" in r["title"] for r in py_res["results"])

    # Search for typescript interface
    ts_res = engine.search_docs("TaskItem priority", max_tokens=500)
    assert ts_res["results"]
    assert any("TaskItem" in r["title"] for r in ts_res["results"])

    small_text = (output / "llms-small.txt").read_text(encoding="utf-8")
    assert "class TaskClient" in small_text or "TaskItem" in small_text


def test_directory_scan_ignores_vendor_and_hidden_dirs(tmp_path):
    # Setup vendor and hidden directories with mock files
    src_dir = tmp_path / "project"
    src_dir.mkdir()
    (src_dir / "valid.py").write_text("def valid_func() -> None: pass\n", encoding="utf-8")
    (src_dir / "valid.ts").write_text("export function validTs(): void {}\n", encoding="utf-8")
    (src_dir / "valid.md").write_text("# Valid Doc\nValid content.\n", encoding="utf-8")

    node_modules = src_dir / "node_modules" / "pkg"
    node_modules.mkdir(parents=True)
    (node_modules / "vendor.ts").write_text("export function vendorTs(): void {}\n", encoding="utf-8")

    venv = src_dir / ".venv" / "lib"
    venv.mkdir(parents=True)
    (venv / "vendor.py").write_text("def venv_func() -> None: pass\n", encoding="utf-8")

    hidden = src_dir / ".hidden_docs"
    hidden.mkdir()
    (hidden / "hidden.md").write_text("# Hidden\nHidden content.\n", encoding="utf-8")

    py_sections = extract_python_sections([src_dir])
    assert len(py_sections) == 1
    assert py_sections[0].title == "def valid_func"

    ts_sections = extract_typescript_sections([src_dir])
    assert len(ts_sections) == 1
    assert ts_sections[0].title == "function validTs"

    out = tmp_path / "out_ignore"
    manifest = build_artifacts(
        output_directory=out,
        markdown_directories=[src_dir],
        python_sources=[src_dir],
        typescript_sources=[src_dir],
    )
    titles = {s["title"] for s in manifest["sections"]}
    assert "def valid_func" in titles
    assert "function validTs" in titles
    assert "Valid Doc" in titles
    assert "def venv_func" not in titles
    assert "function vendorTs" not in titles
    assert "Hidden" not in titles


def test_external_relative_openapi_refs(tmp_path):
    schemas_dir = tmp_path / "schemas"
    schemas_dir.mkdir()
    (schemas_dir / "user.yaml").write_text(
        """
User:
  type: object
  required:
    - id
    - email
  properties:
    id:
      type: string
    email:
      type: string
""",
        encoding="utf-8",
    )

    main_spec = tmp_path / "main.yaml"
    main_spec.write_text(
        """
openapi: "3.0.3"
info:
  title: Multi-File API
  version: "1.0.0"
paths:
  /users:
    get:
      summary: List users
      responses:
        '200':
          description: A list of users
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: "./schemas/user.yaml#/User"
""",
        encoding="utf-8",
    )

    out = tmp_path / "out_external_refs"
    manifest = build_artifacts(output_directory=out, openapi_files=[main_spec])
    assert len(manifest["sections"]) == 1
    full = (out / "llms-full.txt").read_text(encoding="utf-8")
    assert '"email"' in full
    assert '"id"' in full
    assert '"required"' in full

