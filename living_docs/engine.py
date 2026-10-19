from __future__ import annotations

import difflib
import json
import re
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

import tiktoken
import yaml


_TOKENIZER = tiktoken.get_encoding("cl100k_base")
_METHODS = ("get", "post", "put", "patch", "delete")
_SEARCH_WORDS = re.compile(r"[A-Za-z0-9_./{}-]+")


@dataclass(frozen=True)
class Section:
    id: str
    title: str
    path: str
    content: str
    tokens: int
    description: str = ""
    kind: str = "markdown"
    method: str | None = None


def count_tokens(text: str) -> int:
    return len(_TOKENIZER.encode(text))


def _read_openapi(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    document = json.loads(text) if path.suffix.lower() == ".json" else yaml.safe_load(text)
    if not isinstance(document, dict) or not str(document.get("openapi", "")).startswith("3."):
        raise ValueError(f"{path} is not an OpenAPI 3.x document")
    return document


def _resolve_local_refs(value: Any, document: dict[str, Any], seen: frozenset[str] = frozenset()) -> Any:
    if isinstance(value, list):
        return [_resolve_local_refs(item, document, seen) for item in value]
    if not isinstance(value, dict):
        return value

    reference = value.get("$ref")
    result: dict[str, Any] = {}
    if reference is not None:
        if not isinstance(reference, str) or not reference.startswith("#/"):
            raise ValueError(f"Only local OpenAPI references are supported: {reference!r}")
        if reference in seen:
            result["$ref"] = reference
        else:
            target: Any = document
            for part in reference[2:].split("/"):
                part = part.replace("~1", "/").replace("~0", "~")
                if not isinstance(target, dict) or part not in target:
                    raise ValueError(f"OpenAPI reference does not exist: {reference}")
                target = target[part]
            result.update(_resolve_local_refs(target, document, seen | {reference}))

    result.update({
        key: _resolve_local_refs(item, document, seen)
        for key, item in value.items()
        if key != "$ref"
    })
    return result


def _compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _schema_block(schema: Any) -> str:
    if not isinstance(schema, dict):
        return _compact_json(schema)
    return _compact_json(schema)


def _render_operation(path: str, method: str, operation: dict[str, Any], document: dict[str, Any]) -> tuple[str, str]:
    resolved = _resolve_local_refs(operation, document)
    summary = str(resolved.get("summary") or resolved.get("operationId") or f"{method.upper()} {path}")
    description = str(resolved.get("description") or "")
    lines = [f"# `{method.upper()} {path}` — {summary}", ""]
    if description:
        lines.extend((description, ""))

    parameters = resolved.get("parameters", [])
    if parameters:
        lines.extend(("## Parameters", ""))
        for parameter in parameters:
            location = parameter.get("in", "unknown")
            required = ", required" if parameter.get("required") else ""
            schema = parameter.get("schema", {})
            detail = f": {parameter['description']}" if parameter.get("description") else ""
            lines.append(
                f"- `{parameter.get('name', '')}` ({location}{required}){detail} "
                f"Schema: `{_schema_block(schema)}`"
            )
        lines.append("")

    request_body = resolved.get("requestBody")
    if request_body:
        lines.extend(("## Request body", ""))
        lines.append(f"Required: {'yes' if request_body.get('required') else 'no'}")
        if request_body.get("description"):
            lines.extend((str(request_body["description"]), ""))
        for content_type, media in sorted(request_body.get("content", {}).items()):
            lines.append(f"### {content_type}")
            lines.append("```json")
            lines.append(_schema_block(media.get("schema", {})))
            lines.extend(("```", ""))

    responses = resolved.get("responses", {})
    if responses:
        lines.extend(("## Responses", ""))
        for status, response in sorted(responses.items()):
            response_description = response.get("description", "")
            lines.append(f"### {status}{': ' + response_description if response_description else ''}")
            for name, header in sorted(response.get("headers", {}).items()):
                required = ", required" if header.get("required") else ""
                lines.append(
                    f"- Header `{name}`{required}: `{_schema_block(header.get('schema', {}))}`"
                )
            for content_type, media in sorted(response.get("content", {}).items()):
                lines.append(f"#### {content_type}")
                lines.append("```json")
                lines.append(_schema_block(media.get("schema", {})))
                lines.extend(("```", ""))

    security = resolved.get("security", document.get("security"))
    if security:
        lines.extend(("## Security", "", f"`{_compact_json(security)}`", ""))
    return "\n".join(lines).rstrip() + "\n", summary


def _openapi_sections(path: Path) -> list[Section]:
    document = _read_openapi(path)
    sections: list[Section] = []
    for route, raw_path_item in sorted(document.get("paths", {}).items()):
        path_item = _resolve_local_refs(raw_path_item, document)
        if not isinstance(path_item, dict):
            continue
        for method in _METHODS:
            raw_operation = path_item.get(method)
            if not isinstance(raw_operation, dict):
                continue
            operation = dict(raw_operation)
            path_parameters = path_item.get("parameters", [])
            operation_parameters = operation.get("parameters", [])
            if path_parameters:
                combined = {
                    (parameter.get("name"), parameter.get("in")): parameter
                    for parameter in path_parameters
                }
                combined.update({
                    (parameter.get("name"), parameter.get("in")): parameter
                    for parameter in operation_parameters
                })
                operation["parameters"] = list(combined.values())
            content, summary = _render_operation(route, method, operation, document)
            section_id = f"api-{method}-{quote(route, safe='')}"
            sections.append(Section(
                id=section_id,
                title=f"{method.upper()} {route}",
                path=route,
                content=content,
                tokens=count_tokens(content),
                description=summary,
                kind="api",
                method=method.upper(),
            ))
    return sections


def _clean_markdown(text: str) -> str:
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for index in range(1, len(lines)):
            if lines[index].strip() == "---":
                lines = lines[index + 1:]
                break

    output: list[str] = []
    fence: str | None = None
    hidden_tag: str | None = None
    for line in lines:
        stripped = line.strip()
        fence_match = re.match(r"^(```+|~~~+)", stripped)
        if fence_match:
            marker = fence_match.group(1)[0]
            if fence is None:
                fence = marker
            elif marker == fence:
                fence = None
            output.append(line)
            continue
        if fence is not None:
            output.append(line)
            continue
        if (
            re.match(r"^\s*import\s+", line)
            or re.match(r"^\s*export\s+\{", line)
        ):
            continue
        while True:
            if hidden_tag:
                closing = re.search(rf"</{hidden_tag}\s*>", line, flags=re.I)
                if not closing:
                    line = ""
                    break
                line = line[closing.end():]
                hidden_tag = None
            opening = re.search(r"<(script|style)\b[^>]*>", line, flags=re.I)
            if not opening:
                break
            tag = opening.group(1)
            closing = re.search(rf"</{tag}\s*>", line[opening.end():], flags=re.I)
            if not closing:
                line = line[:opening.start()]
                hidden_tag = tag
                break
            closing_end = opening.end() + closing.end()
            line = line[:opening.start()] + line[closing_end:]
        line = re.sub(r"!\[([^\]]*)\]\((?!https?://)[^)]+\)", "", line)
        line = re.sub(r"\[([^\]]+)\]\((?!https?://)[^)]+\)", r"\1", line)
        line = re.sub(r"<(?!https?://)/?[A-Za-z][^>]*>", "", line)
        output.append(line)

    cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(output)).strip()
    return cleaned + ("\n" if cleaned else "")


def _markdown_sections(directories: list[Path]) -> list[Section]:
    sections: list[Section] = []
    for directory in directories:
        for source in sorted((*directory.rglob("*.md"), *directory.rglob("*.mdx"))):
            content = _clean_markdown(source.read_text(encoding="utf-8"))
            if not content:
                continue
            relative = source.relative_to(directory).as_posix()
            title_match = re.search(r"(?m)^#\s+(.+)$", content)
            title = title_match.group(1).strip() if title_match else source.stem.replace("-", " ").title()
            description = next(
                (line.strip() for line in content.splitlines() if line.strip() and not line.startswith("#")),
                "",
            )
            section_id = quote(relative, safe="/")
            sections.append(Section(
                id=f"doc-{section_id}",
                title=title,
                path=f"/{relative}",
                content=content,
                tokens=count_tokens(content),
                description=description[:240],
            ))
    return sections


def _manifest(sections: list[Section], project_name: str) -> dict[str, Any]:
    return {
        "version": "1.0.0",
        "project": project_name,
        "total_tokens": sum(section.tokens for section in sections),
        "sections": [
            {
                "id": section.id,
                "title": section.title,
                "path": section.path,
                "tokens": section.tokens,
                "description": section.description,
                "kind": section.kind,
                **({"method": section.method} if section.method else {}),
            }
            for section in sections
        ],
    }


def build_artifacts(
    output_directory: Path,
    openapi_files: list[Path] | None = None,
    markdown_directories: list[Path] | None = None,
    project_name: str = "Documentation",
    small_token_budget: int = 4000,
) -> dict[str, Any]:
    sections: list[Section] = []
    for path in openapi_files or []:
        sections.extend(_openapi_sections(path))
    sections.extend(_markdown_sections(markdown_directories or []))
    if not sections:
        raise ValueError("No documentation sections were found in the provided sources")

    sections.sort(key=lambda section: (section.path, section.method or "", section.id))
    manifest = _manifest(sections, project_name)
    small_header = f"# {project_name} — compact reference\n\n"
    if small_token_budget < 1 or count_tokens(small_header) > small_token_budget:
        raise ValueError("small_token_budget is too small for the compact-reference header")

    output_directory.mkdir(parents=True, exist_ok=True)
    index = {
        "manifest": manifest,
        "sections": [asdict(section) for section in sections],
    }
    (output_directory / "docs-index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    index_lines = [
        f"# {project_name}",
        "",
        "Machine-optimized documentation index.",
        "",
        f"Total: {manifest['total_tokens']} tokens across {len(sections)} sections.",
        "",
    ]
    for section in sections:
        index_lines.append(f"- [{section.title}]({section.path}) — {section.tokens} tokens")
        if section.description:
            index_lines.append(f"  {section.description}")
    (output_directory / "llms.txt").write_text("\n".join(index_lines) + "\n", encoding="utf-8")

    small_sections: list[Section] = []
    priority_sections = sorted(sections, key=lambda section: (section.kind != "api", section.path, section.id))
    for section in priority_sections:
        candidate_sections = [*small_sections, section]
        candidate_text = small_header + "\n".join(item.content.rstrip() for item in candidate_sections) + "\n"
        if count_tokens(candidate_text) <= small_token_budget:
            small_sections.append(section)
    small_sections.sort(key=lambda section: (section.path, section.method or "", section.id))
    small_text = small_header + "\n".join(section.content.rstrip() for section in small_sections) + "\n"
    (output_directory / "llms-small.txt").write_text(small_text, encoding="utf-8")
    (output_directory / "llms-full.txt").write_text(
        f"# {project_name} — full reference\n\n"
        + "\n".join(section.content.rstrip() for section in sections)
        + "\n",
        encoding="utf-8",
    )
    return manifest


class DocumentationEngine:
    def __init__(self, sections: list[dict[str, Any]], manifest: dict[str, Any]):
        self.sections = sections
        self.manifest = manifest
        self._by_api = {
            (section["path"], section["method"]): section
            for section in sections
            if section.get("kind") == "api" and section.get("method")
        }
        self._database = sqlite3.connect(":memory:")
        self._database.execute(
            "CREATE VIRTUAL TABLE docs USING fts5(id, title, path, description, content)"
        )
        self._database.executemany(
            "INSERT INTO docs VALUES (?, ?, ?, ?, ?)",
            [
                (s["id"], s["title"], s["path"], s.get("description", ""), s["content"])
                for s in sections
            ],
        )

    @classmethod
    def from_index(cls, index_path: Path) -> DocumentationEngine:
        index = json.loads(index_path.read_text(encoding="utf-8"))
        return cls(index["sections"], index["manifest"])

    def search_docs(self, query: str, max_tokens: int = 2000) -> dict[str, Any]:
        if not query.strip():
            return {"status": "error", "error_code": "INVALID_QUERY", "message": "query must not be empty"}
        if max_tokens < 32:
            return {
                "status": "error",
                "error_code": "INVALID_TOKEN_BUDGET",
                "message": "max_tokens must be at least 32",
            }
        terms = _SEARCH_WORDS.findall(query)
        if not terms:
            result: dict[str, Any] = {"results": [], "token_count": 0}
            result["token_count"] = _payload_token_count(result)
            return result
        expression = " OR ".join(f'"{term.replace(chr(34), chr(34) * 2)}"' for term in terms[:32])
        rows = self._database.execute(
            "SELECT id, title, path, description, content, bm25(docs) "
            "FROM docs WHERE docs MATCH ? ORDER BY bm25(docs)",
            (expression,),
        ).fetchall()

        result: dict[str, Any] = {"results": [], "token_count": 0}
        for row in rows:
            candidate = {
                "id": row[0],
                "title": row[1],
                "path": row[2],
                "description": row[3],
                "content": row[4],
            }
            trial = {"results": [*result["results"], candidate], "token_count": 0}
            trial["token_count"] = _payload_token_count(trial)
            if trial["token_count"] > max_tokens:
                continue
            result = trial
        result["token_count"] = _payload_token_count(result)
        return result

    def get_api_spec(self, endpoint_path: str, method: str) -> dict[str, Any]:
        normalized_method = method.upper()
        section = self._by_api.get((endpoint_path, normalized_method))
        if section:
            return {
                "status": "ok",
                "endpoint_path": endpoint_path,
                "method": normalized_method,
                "spec": section["content"],
            }
        available = sorted({
            api_method for path, api_method in self._by_api
            if path == endpoint_path
        })
        known_paths = sorted({path for path, _ in self._by_api})
        suggestions = difflib.get_close_matches(endpoint_path, known_paths, n=3, cutoff=0.35)
        suggested_methods = sorted({
            api_method for path, api_method in self._by_api
            if path in suggestions
        })
        return {
            "status": "error",
            "error_code": "RESOURCE_NOT_FOUND",
            "message": f"Endpoint '{endpoint_path}' with method {normalized_method} does not exist.",
            "context": {
                "requested_path": endpoint_path,
                "suggested_paths": suggestions,
                "valid_methods_for_suggestions": available or suggested_methods,
            },
        }


def _payload_token_count(payload: dict[str, Any]) -> int:
    token_count = payload.get("token_count", 0)
    while True:
        payload["token_count"] = token_count
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        actual_count = count_tokens(encoded)
        if actual_count == token_count:
            return actual_count
        token_count = actual_count
