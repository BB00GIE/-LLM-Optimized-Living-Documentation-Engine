from __future__ import annotations

import difflib
import json
import re
import sqlite3
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

import tiktoken
import yaml

from living_docs.embeddings import (
    Embedder,
    HashingEmbedder,
    cosine_similarity,
    pack_vector,
)


_TOKENIZERS: dict[str, tiktoken.Encoding] = {}
_METHODS = ("get", "post", "put", "patch", "delete")
_SEARCH_WORDS = re.compile(r"[A-Za-z0-9_./{}-]+")


def get_tokenizer(encoding_name: str = "cl100k_base") -> tiktoken.Encoding:
    if encoding_name not in _TOKENIZERS:
        _TOKENIZERS[encoding_name] = tiktoken.get_encoding(encoding_name)
    return _TOKENIZERS[encoding_name]


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


def count_tokens(text: str, encoding_name: str = "cl100k_base") -> int:
    return len(get_tokenizer(encoding_name).encode(text))


def _read_openapi(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    document = json.loads(text) if path.suffix.lower() == ".json" else yaml.safe_load(text)
    if not isinstance(document, dict) or not str(document.get("openapi", "")).startswith("3."):
        raise ValueError(f"{path} is not an OpenAPI 3.x document")
    return document


def _resolve_local_refs(
    value: Any,
    document: dict[str, Any],
    seen: frozenset[str] = frozenset(),
    depth: int = 0,
) -> Any:
    if depth > 64:
        raise ValueError("Exceeded maximum OpenAPI reference recursion depth (64)")
    if isinstance(value, list):
        return [_resolve_local_refs(item, document, seen, depth + 1) for item in value]
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
            result.update(_resolve_local_refs(target, document, seen | {reference}, depth + 1))

    result.update({
        key: _resolve_local_refs(item, document, seen, depth + 1)
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


def _openapi_sections(path: Path, encoding_name: str = "cl100k_base") -> list[Section]:
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
                tokens=count_tokens(content, encoding_name=encoding_name),
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
        parts = re.split(r"(`[^`]+`)", line)
        cleaned_parts = []
        for part in parts:
            if part.startswith("`") and part.endswith("`"):
                cleaned_parts.append(part)
            else:
                p = re.sub(r"!\[([^\]]*)\]\((?!https?://)[^)]+\)", "", part)
                p = re.sub(r"\[([^\]]+)\]\((?!https?://)[^)]+\)", r"\1", p)
                tag_pattern = r"</[A-Za-z][A-Za-z0-9_.:-]*\s*>|(?<![A-Za-z0-9_])<(?!https?://)[A-Za-z][A-Za-z0-9_.:-]*(?:\s+[^>]*)?/?>"
                p = re.sub(tag_pattern, "", p)
                cleaned_parts.append(p)
        output.append("".join(cleaned_parts))

    cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(output)).strip()
    return cleaned + ("\n" if cleaned else "")


def _markdown_sections(directories: list[Path], encoding_name: str = "cl100k_base") -> list[Section]:
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
                tokens=count_tokens(content, encoding_name=encoding_name),
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
    python_sources: list[Path] | None = None,
    typescript_sources: list[Path] | None = None,
    project_name: str = "Documentation",
    small_token_budget: int = 4000,
    encoding_name: str = "cl100k_base",
    embedder: Embedder | None = None,
) -> dict[str, Any]:
    sections: list[Section] = []
    for path in openapi_files or []:
        sections.extend(_openapi_sections(path, encoding_name=encoding_name))
    sections.extend(_markdown_sections(markdown_directories or [], encoding_name=encoding_name))
    if python_sources:
        from living_docs.ast_parser import extract_python_sections
        sections.extend(extract_python_sections(python_sources, encoding_name=encoding_name))
    if typescript_sources:
        from living_docs.ast_parser import extract_typescript_sections
        sections.extend(extract_typescript_sections(typescript_sources, encoding_name=encoding_name))
    if not sections:
        raise ValueError("No documentation sections were found in the provided sources")

    sections.sort(key=lambda section: (section.path, section.method or "", section.id))
    manifest = _manifest(sections, project_name)
    small_header = f"# {project_name} — compact reference\n\n"
    header_tokens = count_tokens(small_header, encoding_name=encoding_name)
    if small_token_budget < 1 or header_tokens > small_token_budget:
        raise ValueError("small_token_budget is too small for the compact-reference header")

    active_embedder = embedder or HashingEmbedder()
    vectors: dict[str, str] = {}
    for section in sections:
        embed_text = f"{section.title}\n{section.description}\n{section.content}"
        vectors[section.id] = pack_vector(active_embedder.embed(embed_text)).hex()

    output_directory.mkdir(parents=True, exist_ok=True)
    index = {
        "manifest": manifest,
        "sections": [asdict(section) for section in sections],
        "encoding_name": encoding_name,
        "vectors": vectors,
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
    accumulated_tokens = header_tokens
    priority_sections = sorted(sections, key=lambda section: (section.kind != "api", section.path, section.id))
    for section in priority_sections:
        if accumulated_tokens + section.tokens + 2 <= small_token_budget:
            candidate_text = small_header + "\n".join(item.content.rstrip() for item in (*small_sections, section)) + "\n"
            exact_tokens = count_tokens(candidate_text, encoding_name=encoding_name)
            if exact_tokens <= small_token_budget:
                small_sections.append(section)
                accumulated_tokens = exact_tokens
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
    def __init__(
        self,
        sections: list[dict[str, Any]],
        manifest: dict[str, Any],
        embedder: Embedder | None = None,
        encoding_name: str = "cl100k_base",
        vectors: dict[str, bytes] | None = None,
    ):
        self.sections = sections
        self.manifest = manifest
        self.embedder: Embedder = embedder if embedder is not None else HashingEmbedder()
        self.encoding_name = encoding_name
        self._sections_by_id = {s["id"]: s for s in sections}
        self._lock = threading.Lock()
        self._by_api = {
            (section["path"], section["method"]): section
            for section in sections
            if section.get("kind") == "api" and section.get("method")
        }
        self._database = sqlite3.connect(":memory:", check_same_thread=False)
        self._database.create_function("cosine_similarity", 2, cosine_similarity)
        self._database.execute(
            "CREATE VIRTUAL TABLE docs USING fts5(id, title, path, description, content)"
        )
        self._database.execute(
            "CREATE TABLE doc_vectors (id TEXT PRIMARY KEY, vector BLOB)"
        )
        self._database.executemany(
            "INSERT INTO docs VALUES (?, ?, ?, ?, ?)",
            [
                (s["id"], s["title"], s["path"], s.get("description", ""), s["content"])
                for s in sections
            ],
        )

        vector_rows = []
        if vectors:
            for s in sections:
                if s["id"] in vectors:
                    vector_rows.append((s["id"], vectors[s["id"]]))
                else:
                    embed_text = f"{s['title']}\n{s.get('description', '')}\n{s['content']}"
                    vector_rows.append((s["id"], pack_vector(self.embedder.embed(embed_text))))
        else:
            for s in sections:
                embed_text = f"{s['title']}\n{s.get('description', '')}\n{s['content']}"
                vector_rows.append((s["id"], pack_vector(self.embedder.embed(embed_text))))
        self._database.executemany("INSERT INTO doc_vectors VALUES (?, ?)", vector_rows)

    @classmethod
    def from_index(
        cls,
        index_path: Path,
        embedder: Embedder | None = None,
        encoding_name: str | None = None,
    ) -> DocumentationEngine:
        index = json.loads(index_path.read_text(encoding="utf-8"))
        actual_encoding = encoding_name or index.get("encoding_name", "cl100k_base")
        raw_vectors = index.get("vectors")
        vectors: dict[str, bytes] | None = None
        if raw_vectors:
            vectors = {doc_id: bytes.fromhex(hex_str) for doc_id, hex_str in raw_vectors.items()}
        return cls(
            index["sections"],
            index["manifest"],
            embedder=embedder,
            encoding_name=actual_encoding,
            vectors=vectors,
        )

    def search_docs(
        self,
        query: str,
        max_tokens: int = 2000,
        bm25_weight: float = 0.5,
        vector_weight: float = 0.5,
    ) -> dict[str, Any]:
        if not query.strip():
            return {"status": "error", "error_code": "INVALID_QUERY", "message": "query must not be empty"}
        if len(query) > 2000:
            return {
                "status": "error",
                "error_code": "INVALID_QUERY",
                "message": "query must not exceed 2000 characters",
            }
        if max_tokens < 32 or max_tokens > 32768:
            return {
                "status": "error",
                "error_code": "INVALID_TOKEN_BUDGET",
                "message": "max_tokens must be between 32 and 32768",
            }

        bm25_ranks: dict[str, int] = {}
        terms = _SEARCH_WORDS.findall(query)
        query_vec: bytes | None = None
        if self.embedder is not None:
            query_vec = pack_vector(self.embedder.embed(query))

        vector_ranks: dict[str, int] = {}
        with self._lock:
            if terms:
                expression = " OR ".join(f'"{term.replace(chr(34), chr(34) * 2)}"' for term in terms[:32])
                try:
                    rows = self._database.execute(
                        "SELECT id, bm25(docs) FROM docs WHERE docs MATCH ? ORDER BY bm25(docs) ASC LIMIT 50",
                        (expression,),
                    ).fetchall()
                    for rank, (doc_id, _) in enumerate(rows, start=1):
                        bm25_ranks[doc_id] = rank
                except sqlite3.OperationalError:
                    pass

            if query_vec is not None:
                vec_rows = self._database.execute(
                    "SELECT id, cosine_similarity(vector, ?) AS sim FROM doc_vectors ORDER BY sim DESC LIMIT 50",
                    (query_vec,),
                ).fetchall()
                for rank, (doc_id, sim) in enumerate(vec_rows, start=1):
                    if sim > 0.0:
                        vector_ranks[doc_id] = rank

        all_candidate_ids = set(bm25_ranks.keys()) | set(vector_ranks.keys())
        if not all_candidate_ids:
            result: dict[str, Any] = {"results": [], "token_count": 0}
            result["token_count"] = _payload_token_count(result, self.encoding_name)
            return result

        k = 60
        scored: list[tuple[float, str]] = []
        for doc_id in all_candidate_ids:
            score = 0.0
            if doc_id in bm25_ranks:
                score += bm25_weight / (k + bm25_ranks[doc_id])
            if doc_id in vector_ranks:
                score += vector_weight / (k + vector_ranks[doc_id])
            scored.append((score, doc_id))

        scored.sort(key=lambda item: item[0], reverse=True)

        result = {"results": [], "token_count": 0}
        current_tokens = _payload_token_count(result, self.encoding_name)
        for _, doc_id in scored:
            s = self._sections_by_id[doc_id]
            if current_tokens + s.get("tokens", 0) > max_tokens + 50:
                continue
            candidate = {
                "id": s["id"],
                "title": s["title"],
                "path": s["path"],
                "description": s.get("description", ""),
                "content": s["content"],
            }
            trial = {"results": [*result["results"], candidate], "token_count": 0}
            trial_tokens = _payload_token_count(trial, self.encoding_name)
            if trial_tokens > max_tokens:
                continue
            result = trial
            current_tokens = trial_tokens
        result["token_count"] = current_tokens
        return result

    def get_api_spec(self, endpoint_path: str, method: str) -> dict[str, Any]:
        normalized_method = method.upper()
        section = self._by_api.get((endpoint_path, normalized_method))
        if not section:
            alt_path = (
                endpoint_path[:-1]
                if endpoint_path.endswith("/") and len(endpoint_path) > 1
                else (endpoint_path + "/")
            )
            section = self._by_api.get((alt_path, normalized_method))
            if section:
                endpoint_path = alt_path

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


def _payload_token_count(payload: dict[str, Any], encoding_name: str = "cl100k_base") -> int:
    token_count = payload.get("token_count", 0)
    while True:
        payload["token_count"] = token_count
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        actual_count = count_tokens(encoded, encoding_name=encoding_name)
        if actual_count == token_count:
            return actual_count
        token_count = actual_count
