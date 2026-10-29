"""Client SDK Exporter / Typed Stubs Generator.

Generates zero-dependency, type-safe Python and TypeScript client stubs
directly from documentation index artifacts (docs-index.json) or parsed OpenAPI specs.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal


@dataclass
class EndpointParameter:
    name: str
    location: str  # query, path, header, cookie
    required: bool
    schema_dict: dict[str, Any]
    description: str = ""


@dataclass
class EndpointOperation:
    method: str
    path: str
    operation_id: str
    summary: str
    parameters: list[EndpointParameter]
    request_body_schema: dict[str, Any] | None
    response_schema: dict[str, Any] | None


def _clean_identifier(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", name)
    if cleaned and cleaned[0].isdigit():
        cleaned = f"_{cleaned}"
    return cleaned or "item"


def _to_snake_case(name: str) -> str:
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    s2 = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1)
    s3 = re.sub(r"[^A-Za-z0-9_]+", "_", s2)
    s4 = s3.strip("_").lower()
    if s4 and s4[0].isdigit():
        s4 = f"_{s4}"
    return s4 or "endpoint"


def _to_camel_case(name: str) -> str:
    parts = re.split(r"[^A-Za-z0-9]+", name)
    parts = [p for p in parts if p]
    if not parts:
        return "endpoint"
    first = parts[0].lower()
    rest = "".join(p.capitalize() for p in parts[1:])
    return first + rest


def _to_pascal_case(name: str) -> str:
    parts = re.split(r"[^A-Za-z0-9]+", name)
    parts = [p.capitalize() for p in parts if p]
    return "".join(parts) or "Model"


def _parse_endpoints_from_sections(sections: list[dict[str, Any]]) -> list[EndpointOperation]:
    """Parse API operations from section content or metadata."""
    operations: list[EndpointOperation] = []

    for section in sections:
        if section.get("kind") != "api" or not section.get("method"):
            continue

        method = section["method"].upper()
        path = section.get("path", "")
        summary = section.get("description", "")
        content = section.get("content", "")

        # Extract operation name / summary
        op_id = ""
        first_line = content.splitlines()[0] if content else ""
        if "—" in first_line:
            raw_summary = first_line.split("—", 1)[1].strip()
            # If the summary is a valid camelCase or PascalCase identifier, use it as op_id
            if re.match(r"^[A-Za-z][A-Za-z0-9_]*$", raw_summary):
                op_id = raw_summary
            summary = raw_summary

        # Parse parameters
        parameters: list[EndpointParameter] = []
        param_pattern = re.compile(
            r"-\s*`([^`]+)`\s*\(([^,)]+)(?:,\s*(required))?\)(?::\s*([^\n`]+?))?\s*Schema:\s*`(\{.*?\})`"
        )
        for match in param_pattern.finditer(content):
            p_name = match.group(1).strip()
            p_loc = match.group(2).strip()
            p_req = match.group(3) == "required"
            p_desc = match.group(4).strip() if match.group(4) else ""
            try:
                p_schema = json.loads(match.group(5))
            except Exception:
                p_schema = {}
            parameters.append(
                EndpointParameter(
                    name=p_name,
                    location=p_loc,
                    required=p_req,
                    schema_dict=p_schema,
                    description=p_desc,
                )
            )

        # Parse request body schema
        req_body_schema: dict[str, Any] | None = None
        req_body_match = re.search(
            r"## Request body.*?```json\s*([\s\S]*?)\s*```",
            content,
            re.DOTALL,
        )
        if req_body_match:
            try:
                req_body_schema = json.loads(req_body_match.group(1))
            except Exception:
                req_body_schema = None

        # Parse primary response schema (e.g. 200/201)
        resp_schema: dict[str, Any] | None = None
        resp_match = re.search(
            r"## Responses\s*.*?###\s*2\d\d.*?```json\s*([\s\S]*?)\s*```",
            content,
            re.DOTALL,
        )
        if resp_match:
            try:
                resp_schema = json.loads(resp_match.group(1))
            except Exception:
                resp_schema = None

        if not op_id:
            # Generate operation ID from method + path
            path_parts = [p for p in re.split(r"[{}/_-]+", path) if p]
            op_id = method.lower() + "".join(p.capitalize() for p in path_parts)

        operations.append(
            EndpointOperation(
                method=method,
                path=path,
                operation_id=op_id,
                summary=summary,
                parameters=parameters,
                request_body_schema=req_body_schema,
                response_schema=resp_schema,
            )
        )

    return operations


def _py_type_from_schema(schema: dict[str, Any] | None, model_name: str, collected_models: dict[str, str]) -> str:
    if not schema or not isinstance(schema, dict):
        return "Any"

    t = schema.get("type")
    if t == "string":
        return "str"
    elif t in ("integer", "int"):
        return "int"
    elif t in ("number", "float"):
        return "float"
    elif t == "boolean":
        return "bool"
    elif t == "array":
        item_schema = schema.get("items")
        item_type = _py_type_from_schema(item_schema, f"{model_name}Item", collected_models)
        return f"list[{item_type}]"
    elif t == "object" or "properties" in schema:
        properties = schema.get("properties", {})
        if not properties:
            return "dict[str, Any]"

        model_cls_name = _to_pascal_case(model_name)
        if model_cls_name not in collected_models:
            req_fields = set(schema.get("required", []))
            lines = [f"class {model_cls_name}(TypedDict, total=False):"]
            prop_lines: list[str] = []
            for prop_name, prop_def in properties.items():
                safe_name = _clean_identifier(prop_name)
                prop_type = _py_type_from_schema(prop_def, f"{model_cls_name}{_to_pascal_case(prop_name)}", collected_models)
                # In TypedDict total=False, indicate required if any
                req_comment = "  # required" if prop_name in req_fields else ""
                prop_lines.append(f"    {safe_name}: {prop_type}{req_comment}")
            if not prop_lines:
                lines.append("    pass")
            else:
                lines.extend(prop_lines)
            collected_models[model_cls_name] = "\n".join(lines)
        return model_cls_name

    return "Any"


def _ts_type_from_schema(schema: dict[str, Any] | None, model_name: str, collected_models: dict[str, str]) -> str:
    if not schema or not isinstance(schema, dict):
        return "any"

    t = schema.get("type")
    if t == "string":
        enum_vals = schema.get("enum")
        if enum_vals and isinstance(enum_vals, list):
            return " | ".join(f'"{v}"' for v in enum_vals)
        return "string"
    elif t in ("integer", "int", "number", "float"):
        return "number"
    elif t == "boolean":
        return "boolean"
    elif t == "array":
        item_schema = schema.get("items")
        item_type = _ts_type_from_schema(item_schema, f"{model_name}Item", collected_models)
        return f"{item_type}[]"
    elif t == "object" or "properties" in schema:
        properties = schema.get("properties", {})
        if not properties:
            return "Record<string, any>"

        model_interface_name = _to_pascal_case(model_name)
        if model_interface_name not in collected_models:
            req_fields = set(schema.get("required", []))
            lines = [f"export interface {model_interface_name} {{"]
            for prop_name, prop_def in properties.items():
                is_req = prop_name in req_fields
                prop_type = _ts_type_from_schema(prop_def, f"{model_interface_name}{_to_pascal_case(prop_name)}", collected_models)
                opt = "" if is_req else "?"
                lines.append(f"  {prop_name}{opt}: {prop_type};")
            lines.append("}")
            collected_models[model_interface_name] = "\n".join(lines)
        return model_interface_name

    return "any"


def generate_python_stubs(
    operations: list[EndpointOperation],
    client_name: str = "LivingDocsApiClient",
    project_name: str = "Living Docs API",
) -> str:
    """Generate self-contained Python client stubs with TypedDict models and type hints."""
    collected_models: dict[str, str] = {}
    methods_code: list[str] = []

    for op in operations:
        base_name = _to_pascal_case(op.operation_id)
        req_type = "Any"
        if op.request_body_schema:
            req_type = _py_type_from_schema(op.request_body_schema, f"{base_name}Request", collected_models)

        resp_type = "Any"
        if op.response_schema:
            resp_type = _py_type_from_schema(op.response_schema, f"{base_name}Response", collected_models)

        # Build method args
        py_method_name = _to_snake_case(op.operation_id)
        method_args = ["self"]

        # Path params
        path_params = [p for p in op.parameters if p.location == "path"]
        for p in path_params:
            p_type = _py_type_from_schema(p.schema_dict, f"{base_name}{_to_pascal_case(p.name)}", collected_models)
            method_args.append(f"{_clean_identifier(p.name)}: {p_type}")

        # Request body
        if op.request_body_schema:
            method_args.append(f"payload: {req_type}")

        # Query params
        query_params = [p for p in op.parameters if p.location == "query"]
        for p in query_params:
            p_type = _py_type_from_schema(p.schema_dict, f"{base_name}{_to_pascal_case(p.name)}", collected_models)
            if not p.required:
                method_args.append(f"{_clean_identifier(p.name)}: {p_type} | None = None")
            else:
                method_args.append(f"{_clean_identifier(p.name)}: {p_type}")

        # Format URL template replacement
        url_expr = f'f"{{self.base_url}}{op.path}"'
        docstring_summary = op.summary or f"{op.method} {op.path}"

        method_lines = [
            f"    def {py_method_name}({', '.join(method_args)}) -> {resp_type}:",
            f'        """{op.method} {op.path} — {docstring_summary}"""',
            f"        url = {url_expr}",
            "        # Zero-dependency execution stub; implement with urllib.request or httpx",
            f"        return {resp_type}() if {resp_type} is not Any else {{}}",  # type: ignore
        ]
        methods_code.append("\n".join(method_lines))

    output: list[str] = [
        '"""Auto-generated Python client stubs from Living Documentation Engine."""',
        "",
        "from __future__ import annotations",
        "",
        "from typing import Any, TypedDict",
        "",
        "",
    ]

    # Models section
    if collected_models:
        output.append("# --- Type Models ---")
        output.append("")
        for model_str in collected_models.values():
            output.append(model_str)
            output.append("")
        output.append("")

    # Client class
    output.append(f"class {client_name}:")
    output.append(f'    """Client interface for {project_name}."""')
    output.append("")
    output.append('    def __init__(self, base_url: str = "http://localhost:8000"):')
    output.append("        self.base_url = base_url.rstrip('/')")
    output.append("")

    if methods_code:
        output.append("\n\n".join(methods_code))
    else:
        output.append("    pass")

    output.append("")
    return "\n".join(output)


def generate_typescript_stubs(
    operations: list[EndpointOperation],
    client_name: str = "LivingDocsApiClient",
    project_name: str = "Living Docs API",
) -> str:
    """Generate self-contained TypeScript client stubs with interfaces and typed methods."""
    collected_models: dict[str, str] = {}
    methods_code: list[str] = []

    for op in operations:
        base_name = _to_pascal_case(op.operation_id)
        req_type = "any"
        if op.request_body_schema:
            req_type = _ts_type_from_schema(op.request_body_schema, f"{base_name}Request", collected_models)

        resp_type = "any"
        if op.response_schema:
            resp_type = _ts_type_from_schema(op.response_schema, f"{base_name}Response", collected_models)

        ts_method_name = _to_camel_case(op.operation_id)
        method_args: list[str] = []

        path_params = [p for p in op.parameters if p.location == "path"]
        for p in path_params:
            p_type = _ts_type_from_schema(p.schema_dict, f"{base_name}{_to_pascal_case(p.name)}", collected_models)
            method_args.append(f"{_clean_identifier(p.name)}: {p_type}")

        if op.request_body_schema:
            method_args.append(f"payload: {req_type}")

        query_params = [p for p in op.parameters if p.location == "query"]
        for p in query_params:
            p_type = _ts_type_from_schema(p.schema_dict, f"{base_name}{_to_pascal_case(p.name)}", collected_models)
            opt = "" if p.required else "?"
            method_args.append(f"{_clean_identifier(p.name)}{opt}: {p_type}")

        # TS template string replacement for path params e.g. {task_id} -> ${task_id}
        ts_path = re.sub(r"\{([^}]+)\}", r"${\1}", op.path)
        docstring_summary = op.summary or f"{op.method} {op.path}"

        method_lines = [
            "  /**",
            f"   * {op.method} {op.path} — {docstring_summary}",
            "   */",
            f"  async {ts_method_name}({', '.join(method_args)}): Promise<{resp_type}> {{",
            f"    const url = `${{this.baseUrl}}{ts_path}`;",
            "    // Zero-dependency execution stub; implement with global fetch()",
            f"    return {{}} as {resp_type};",
            "  }",
        ]
        methods_code.append("\n".join(method_lines))

    output: list[str] = [
        "/**",
        " * Auto-generated TypeScript client stubs from Living Documentation Engine.",
        " */",
        "",
    ]

    # Models section
    if collected_models:
        for model_str in collected_models.values():
            output.append(model_str)
            output.append("")

    # Client class
    output.append(f"export class {client_name} {{")
    output.append('  constructor(public baseUrl: string = "http://localhost:8000") {')
    output.append("    this.baseUrl = baseUrl.replace(/\\/+$/, '');")
    output.append("  }")
    output.append("")

    if methods_code:
        output.append("\n\n".join(methods_code))

    output.append("}")
    output.append("")
    return "\n".join(output)


def export_client_stubs(
    index_path: Path,
    lang: Literal["python", "typescript"],
    output_path: Path | None = None,
    client_name: str | None = None,
) -> str:
    """Read docs-index.json, extract API operations, and generate typed client stubs."""
    if not index_path.exists():
        raise FileNotFoundError(f"Documentation index not found: {index_path}")

    index_data = json.loads(index_path.read_text(encoding="utf-8"))
    sections = index_data.get("sections", [])
    manifest = index_data.get("manifest", {})
    project_name = manifest.get("project", "Living Docs API")

    operations = _parse_endpoints_from_sections(sections)
    if not operations:
        raise ValueError(f"No API endpoint operations found in index: {index_path}")

    resolved_client_name = client_name or f"{_to_pascal_case(project_name)}Client"

    if lang == "python":
        code = generate_python_stubs(operations, client_name=resolved_client_name, project_name=project_name)
    elif lang == "typescript":
        code = generate_typescript_stubs(operations, client_name=resolved_client_name, project_name=project_name)
    else:
        raise ValueError(f"Unsupported stub language: {lang!r}")

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(code, encoding="utf-8")

    return code
