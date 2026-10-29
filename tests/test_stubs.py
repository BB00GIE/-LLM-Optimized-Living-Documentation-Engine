from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from living_docs.engine import build_artifacts
from living_docs.stubs import export_client_stubs, generate_python_stubs, generate_typescript_stubs, _parse_endpoints_from_sections


def test_stubs_generation_python(tmp_path: Path):
    index_dir = tmp_path / "build"
    build_artifacts(
        output_directory=index_dir,
        openapi_files=[Path("examples/openapi.yaml")],
        project_name="Example Tasks API",
    )

    py_output = tmp_path / "client.py"
    code = export_client_stubs(
        index_path=index_dir / "docs-index.json",
        lang="python",
        output_path=py_output,
        client_name="TasksTestClient",
    )

    assert py_output.exists()
    assert py_output.read_text(encoding="utf-8") == code

    # Validate that generated Python code is syntactically valid via ast.parse
    parsed_ast = ast.parse(code)
    assert parsed_ast is not None

    assert "class TasksTestClient:" in code
    assert "class Postapitasksrequest(TypedDict, total=False):" in code
    assert "def post_api_tasks(" in code or "def create_task(" in code
    assert "def get_api_tasks(" in code or "def list_tasks(" in code


def test_stubs_generation_typescript(tmp_path: Path):
    index_dir = tmp_path / "build"
    build_artifacts(
        output_directory=index_dir,
        openapi_files=[Path("examples/openapi.yaml")],
        project_name="Example Tasks API",
    )

    ts_output = tmp_path / "client.ts"
    code = export_client_stubs(
        index_path=index_dir / "docs-index.json",
        lang="typescript",
        output_path=ts_output,
        client_name="TasksTestTsClient",
    )

    assert ts_output.exists()
    assert "export class TasksTestTsClient {" in code
    assert "export interface Postapitasksrequest {" in code
    assert "baseUrl: string = \"http://localhost:8000\"" in code
    assert "async postapitasks(" in code or "async createTask(" in code


def test_stubs_error_handling(tmp_path: Path):
    missing_index = tmp_path / "nonexistent.json"
    with pytest.raises(FileNotFoundError):
        export_client_stubs(missing_index, lang="python")

    empty_index = tmp_path / "empty.json"
    empty_index.write_text(json.dumps({"manifest": {}, "sections": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="No API endpoint operations found"):
        export_client_stubs(empty_index, lang="python")


def test_complex_posthog_spec_stubs(tmp_path: Path):
    index_dir = tmp_path / "posthog_build"
    build_artifacts(
        output_directory=index_dir,
        openapi_files=[Path("examples/posthog_production_spec.yaml")],
        project_name="PostHog API",
    )

    py_code = export_client_stubs(
        index_path=index_dir / "docs-index.json",
        lang="python",
        client_name="PostHogApiClient",
    )
    # Syntax check
    assert ast.parse(py_code) is not None
    assert "class PostHogApiClient:" in py_code

    ts_code = export_client_stubs(
        index_path=index_dir / "docs-index.json",
        lang="typescript",
        client_name="PostHogApiClient",
    )
    assert "export class PostHogApiClient {" in ts_code
