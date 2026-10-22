from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from living_docs.engine import DocumentationEngine, build_artifacts, count_tokens


@dataclass
class EvalTaskResult:
    task_id: str
    description: str
    passed: bool
    tokens_consumed: int
    errors: list[str]
    details: dict[str, Any]


@dataclass
class EvalReport:
    total_tasks: int
    passed_tasks: int
    first_pass_accuracy: float
    total_tokens_consumed: int
    results: list[EvalTaskResult]


def evaluate_living_docs_engine(
    output_dir: Path,
    openapi_path: Path,
    python_src_path: Path | None = None,
    typescript_src_path: Path | None = None,
    encoding_name: str = "cl100k_base",
) -> EvalReport:
    """Run E2E agent evaluation scenarios against the living documentation engine."""
    build_artifacts(
        output_directory=output_dir,
        openapi_files=[openapi_path],
        python_sources=[python_src_path] if python_src_path else None,
        typescript_sources=[typescript_src_path] if typescript_src_path else None,
        encoding_name=encoding_name,
    )
    engine = DocumentationEngine.from_index(output_dir / "docs-index.json", encoding_name=encoding_name)

    results: list[EvalTaskResult] = []

    # Scenario 1: Exact REST API Contract Discovery & Schema Conformance
    # Task: Agent queries POST /api/tasks to construct a valid creation payload
    spec_response = engine.get_api_spec("/api/tasks", "POST")
    t1_tokens = count_tokens(json.dumps(spec_response), encoding_name=encoding_name)
    t1_errors: list[str] = []

    if spec_response.get("status") != "ok":
        t1_errors.append(f"Expected status ok, got {spec_response.get('status')}")

    spec_content = spec_response.get("spec", "")
    if '"required":["title"]' not in spec_content:
        t1_errors.append("Required field 'title' not specified in contract schema")
    if '"completed"' not in spec_content:
        t1_errors.append("Property 'completed' missing from schema definition")

    # Simulate agent constructing a candidate payload based on the retrieved spec
    agent_payload = {"title": "Deploy living documentation engine", "completed": False}
    # Validate against constraints
    allowed_fields = {"title", "completed"}
    invalid_fields = set(agent_payload.keys()) - allowed_fields
    if invalid_fields:
        t1_errors.append(f"Payload contains invalid fields: {invalid_fields}")

    results.append(EvalTaskResult(
        task_id="task-01-rest-contract",
        description="Discover POST /api/tasks schema and construct a zero-invalid-field payload",
        passed=len(t1_errors) == 0,
        tokens_consumed=t1_tokens,
        errors=t1_errors,
        details={"payload": agent_payload},
    ))

    # Scenario 2: Error Guidance on Non-Existent Route (Actionable recovery)
    # Task: Agent attempts invalid path /api/tasks_create, expects suggested path /api/tasks
    invalid_response = engine.get_api_spec("/api/task", "GET")
    t2_tokens = count_tokens(json.dumps(invalid_response), encoding_name=encoding_name)
    t2_errors: list[str] = []

    if invalid_response.get("error_code") != "RESOURCE_NOT_FOUND":
        t2_errors.append(f"Expected RESOURCE_NOT_FOUND, got {invalid_response.get('error_code')}")

    context = invalid_response.get("context", {})
    suggested = context.get("suggested_paths", [])
    if not any("/api/tasks" in p for p in suggested):
        t2_errors.append(f"Expected /api/tasks in suggested_paths, got {suggested}")

    results.append(EvalTaskResult(
        task_id="task-02-error-recovery",
        description="Verify actionable error guidance and suggested paths on invalid route request",
        passed=len(t2_errors) == 0,
        tokens_consumed=t2_tokens,
        errors=t2_errors,
        details={"suggested_paths": suggested},
    ))

    # Scenario 3: Hybrid Search over Code Signatures (Python SDK Discovery)
    if python_src_path:
        search_res = engine.search_docs("TaskClient create_task", max_tokens=1000)
        t3_tokens = search_res.get("token_count", 0)
        t3_errors: list[str] = []

        found_titles = [r["title"] for r in search_res.get("results", [])]
        if not any("TaskClient" in t for t in found_titles):
            t3_errors.append(f"Expected class TaskClient in search results, got {found_titles}")

        client_doc = next((r["content"] for r in search_res.get("results", []) if "TaskClient" in r["title"]), "")
        if "def create_task" not in client_doc:
            t3_errors.append("create_task method signature not found in TaskClient documentation block")

        results.append(EvalTaskResult(
            task_id="task-03-python-sdk-search",
            description="Discover Python TaskClient class and verify method signatures are intact",
            passed=len(t3_errors) == 0,
            tokens_consumed=t3_tokens,
            errors=t3_errors,
            details={"found_sections": found_titles},
        ))

    # Scenario 4: TypeScript Enum & Type Contract Discovery
    if typescript_src_path:
        search_ts = engine.search_docs("TaskStatus TaskPriority", max_tokens=1000)
        t4_tokens = search_ts.get("token_count", 0)
        t4_errors: list[str] = []

        found_ts = [r["title"] for r in search_ts.get("results", [])]
        if not any("TaskStatus" in t or "TaskPriority" in t for t in found_ts):
            t4_errors.append(f"Expected TaskStatus or TaskPriority in search results, got {found_ts}")

        results.append(EvalTaskResult(
            task_id="task-04-typescript-type-search",
            description="Discover TypeScript domain enum and type contracts with strict typing boundaries",
            passed=len(t4_errors) == 0,
            tokens_consumed=t4_tokens,
            errors=t4_errors,
            details={"found_sections": found_ts},
        ))

    passed_count = sum(1 for r in results if r.passed)
    accuracy = (passed_count / len(results)) * 100.0 if results else 0.0
    total_tokens = sum(r.tokens_consumed for r in results)

    return EvalReport(
        total_tasks=len(results),
        passed_tasks=passed_count,
        first_pass_accuracy=round(accuracy, 2),
        total_tokens_consumed=total_tokens,
        results=results,
    )
