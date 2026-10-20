from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from living_docs.engine import count_tokens


@dataclass
class BenchmarkResult:
    scenario: str
    raw_tokens: int
    optimized_tokens: int
    tokens_saved: int
    reduction_percentage: float
    schema_preserved: bool


SAMPLE_HTML_DOCUMENTATION = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>API Reference - Create Task | DevPortal</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 0; }
    .navbar { background: #1a1a2e; color: #fff; padding: 1rem 2rem; display: flex; justify-content: space-between; }
    .sidebar { width: 280px; background: #f8f9fa; border-right: 1px solid #e9ecef; height: 100vh; position: fixed; }
    .content { margin-left: 300px; padding: 2rem 4rem; max-width: 900px; line-height: 1.6; }
    .callout { background: #e7f5ff; border-left: 4px solid #339af0; padding: 1rem; border-radius: 4px; margin: 1rem 0; }
    .footer { border-top: 1px solid #dee2e6; margin-top: 4rem; padding: 2rem; color: #868e96; text-align: center; }
  </style>
  <script>
    window.analytics = window.analytics || [];
    function trackPageView() { console.log("page viewed: tasks-api-create"); }
    window.addEventListener("DOMContentLoaded", trackPageView);
  </script>
</head>
<body>
  <header class="navbar">
    <div class="logo">
      <svg width="24" height="24" viewBox="0 0 24 24"><path fill="currentColor" d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>
      <span>DevPortal Cloud Platform</span>
    </div>
    <nav class="nav-links">
      <a href="/products">Products</a>
      <a href="/solutions">Solutions</a>
      <a href="/pricing">Pricing</a>
      <a href="/docs" class="active">Documentation</a>
      <a href="/support">Support</a>
      <button class="btn-signin">Sign In</button>
    </nav>
  </header>

  <aside class="sidebar">
    <div class="search-box"><input type="search" placeholder="Search documentation..."></div>
    <ul class="nav-tree">
      <li><strong>Getting Started</strong></li>
      <li><a href="/docs/overview">Platform Overview</a></li>
      <li><a href="/docs/auth">Authentication & API Keys</a></li>
      <li><a href="/docs/rate-limits">Rate Limits & Quotas</a></li>
      <li><a href="/docs/sdks">Official Client Libraries</a></li>
      <li><strong>Tasks API Reference</strong></li>
      <li><a href="/docs/tasks/list">List All Tasks</a></li>
      <li><a href="/docs/tasks/create" class="active">Create a Task</a></li>
      <li><a href="/docs/tasks/get">Retrieve a Task</a></li>
      <li><a href="/docs/tasks/update">Update a Task</a></li>
      <li><a href="/docs/tasks/delete">Delete a Task</a></li>
      <li><strong>Webhooks & Events</strong></li>
      <li><a href="/docs/webhooks">Webhook Deliveries</a></li>
      <li><a href="/docs/events">Event Catalog</a></li>
    </ul>
  </aside>

  <main class="content">
    <div class="breadcrumb">
      <a href="/docs">Docs</a> &gt; <a href="/docs/tasks">Tasks API</a> &gt; <span>Create Task</span>
    </div>

    <h1>Create a Task</h1>
    <p class="subtitle">Programmatically create a new task item in your workspace queue.</p>

    <div class="callout">
      <strong>Pro Tip:</strong> Ensure your API key has the <code>tasks:write</code> scope assigned before attempting to create new task records.
    </div>

    <h2>Endpoint Overview</h2>
    <p>This endpoint allows external agents, backend services, and automated pipelines to insert task records. When a task is created, asynchronous background workers will index it and notify configured webhook endpoints.</p>

    <h3>HTTP Request</h3>
    <pre><code>POST https://api.devportal.com/v1/api/tasks</code></pre>

    <h3>Request Headers</h3>
    <table border="1">
      <thead><tr><th>Header</th><th>Type</th><th>Required</th><th>Description</th></tr></thead>
      <tbody>
        <tr><td>Authorization</td><td>string</td><td>Yes</td><td>Bearer token formatted as <code>Bearer sec_live_...</code></td></tr>
        <tr><td>Content-Type</td><td>string</td><td>Yes</td><td>Must be <code>application/json</code></td></tr>
      </tbody>
    </table>

    <h3>Request Body Schema</h3>
    <p>Please send a JSON payload containing the task parameters. Below is the specification of accepted properties:</p>
    <ul>
      <li><code>title</code> (string, required): A concise summary of the task to be completed. Must be between 1 and 255 characters.</li>
      <li><code>completed</code> (boolean, optional): Initial completion flag. Defaults to <code>false</code>.</li>
    </ul>

    <h3>Response Status Codes</h3>
    <ul>
      <li><code>201 Created</code>: Task was created successfully. Returns the persisted Task object.</li>
      <li><code>400 Bad Request</code>: Missing required field <code>title</code> or invalid JSON syntax.</li>
      <li><code>401 Unauthorized</code>: Missing or invalid API credentials.</li>
    </ul>

    <h3>Sample Response</h3>
    <pre><code>{
  "id": "tsk_9f82c40b",
  "title": "Process nightly analytics batch",
  "completed": false
}</code></pre>
  </main>

  <footer class="footer">
    <p>&copy; 2026 DevPortal Technologies, Inc. All rights reserved.</p>
  </footer>
</body>
</html>"""


SAMPLE_RAW_OPENAPI_SPEC = {
    "openapi": "3.0.3",
    "info": {"title": "Tasks API", "version": "1.0.0"},
    "paths": {
        "/api/tasks": {
            "post": {
                "summary": "Create a task",
                "operationId": "createTask",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["title"],
                                "properties": {
                                    "title": {"type": "string", "description": "Task title"},
                                    "completed": {"type": "boolean", "default": False, "description": "Completion flag"},
                                },
                            }
                        }
                    },
                },
                "responses": {
                    "201": {
                        "description": "The created task.",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["id", "title"],
                                    "properties": {
                                        "id": {"type": "string"},
                                        "title": {"type": "string"},
                                        "completed": {"type": "boolean"},
                                    },
                                }
                            }
                        },
                    }
                },
            }
        }
    },
}


def run_token_efficiency_benchmark(encoding_name: str = "cl100k_base") -> list[BenchmarkResult]:
    """Compare raw human/spec documentation against living-docs optimized outputs."""
    from living_docs.engine import _render_operation

    # 1. Benchmark: Human HTML Web Docs vs Living Docs Schema Contract
    raw_html_tokens = count_tokens(SAMPLE_HTML_DOCUMENTATION, encoding_name=encoding_name)

    operation = SAMPLE_RAW_OPENAPI_SPEC["paths"]["/api/tasks"]["post"]
    optimized_spec, _ = _render_operation("/api/tasks", "post", operation, SAMPLE_RAW_OPENAPI_SPEC)
    optimized_tokens = count_tokens(optimized_spec, encoding_name=encoding_name)

    schema_preserved = (
        "/api/tasks" in optimized_spec
        and "POST" in optimized_spec
        and '"required":["title"]' in optimized_spec
        and '"required":["id","title"]' in optimized_spec
        and "title" in optimized_spec
        and "completed" in optimized_spec
    )

    savings_1 = raw_html_tokens - optimized_tokens
    reduction_pct_1 = (savings_1 / raw_html_tokens) * 100.0

    result_1 = BenchmarkResult(
        scenario="Human HTML Web Docs vs Living Docs Schema (POST /api/tasks)",
        raw_tokens=raw_html_tokens,
        optimized_tokens=optimized_tokens,
        tokens_saved=savings_1,
        reduction_percentage=round(reduction_pct_1, 2),
        schema_preserved=schema_preserved,
    )

    # 2. Benchmark: Raw JSON OpenAPI Spec vs Compact Rendered Schema
    raw_openapi_json = json.dumps(SAMPLE_RAW_OPENAPI_SPEC, indent=2)
    raw_openapi_tokens = count_tokens(raw_openapi_json, encoding_name=encoding_name)

    savings_2 = raw_openapi_tokens - optimized_tokens
    reduction_pct_2 = (savings_2 / raw_openapi_tokens) * 100.0

    result_2 = BenchmarkResult(
        scenario="Raw OpenAPI JSON Spec vs Living Docs Schema (POST /api/tasks)",
        raw_tokens=raw_openapi_tokens,
        optimized_tokens=optimized_tokens,
        tokens_saved=savings_2,
        reduction_percentage=round(reduction_pct_2, 2),
        schema_preserved=schema_preserved,
    )

    return [result_1, result_2]
