from __future__ import annotations

import ast
import re
from pathlib import Path
from urllib.parse import quote

from living_docs.engine import Section, count_tokens


def _format_py_arg(arg: ast.arg, default: ast.expr | None = None) -> str:
    type_str = f": {ast.unparse(arg.annotation)}" if arg.annotation else ""
    default_str = f" = {ast.unparse(default)}" if default else ""
    return f"{arg.arg}{type_str}{default_str}"


def _format_py_function_signature(node: ast.FunctionDef | ast.AsyncFunctionDef, is_method: bool = False) -> str:
    prefix = "async def " if isinstance(node, ast.AsyncFunctionDef) else "def "
    args = node.args
    arg_strs: list[str] = []

    posonly_args = list(getattr(args, "posonlyargs", []))
    pos_args = list(args.args)

    if is_method:
        if posonly_args and posonly_args[0].arg in ("self", "cls"):
            posonly_args = posonly_args[1:]
        elif pos_args and pos_args[0].arg in ("self", "cls"):
            pos_args = pos_args[1:]

    all_pos = posonly_args + pos_args
    defaults = [None] * (len(all_pos) - len(args.defaults)) + list(args.defaults)
    posonly_defaults = defaults[: len(posonly_args)]
    standard_defaults = defaults[len(posonly_args) :]

    for arg, default in zip(posonly_args, posonly_defaults):
        arg_strs.append(_format_py_arg(arg, default))
    if posonly_args:
        arg_strs.append("/")

    for arg, default in zip(pos_args, standard_defaults):
        arg_strs.append(_format_py_arg(arg, default))

    if args.vararg:
        type_str = f": {ast.unparse(args.vararg.annotation)}" if args.vararg.annotation else ""
        arg_strs.append(f"*{args.vararg.arg}{type_str}")
    elif args.kwonlyargs:
        arg_strs.append("*")

    kw_defaults = list(args.kw_defaults)
    for arg, default in zip(args.kwonlyargs, kw_defaults):
        arg_strs.append(_format_py_arg(arg, default))

    if args.kwarg:
        type_str = f": {ast.unparse(args.kwarg.annotation)}" if args.kwarg.annotation else ""
        arg_strs.append(f"**{args.kwarg.arg}{type_str}")

    returns_str = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    return f"{prefix}{node.name}({', '.join(arg_strs)}){returns_str}"


def _render_py_function(node: ast.FunctionDef | ast.AsyncFunctionDef, rel_path: str, encoding_name: str) -> Section:
    sig = _format_py_function_signature(node)
    doc = ast.get_docstring(node) or ""
    lines = [f"# `{sig}`", ""]
    if doc:
        lines.extend((doc.strip(), ""))
    content = "\n".join(lines).rstrip() + "\n"
    first_doc_line = doc.strip().splitlines()[0] if doc.strip() else f"Function {node.name}"
    return Section(
        id=f"py-{quote(rel_path, safe='')}-{node.name}",
        title=f"def {node.name}",
        path=f"{rel_path}:{node.name}",
        content=content,
        tokens=count_tokens(content, encoding_name=encoding_name),
        description=first_doc_line[:240],
        kind="code",
    )


def _render_py_class(node: ast.ClassDef, rel_path: str, encoding_name: str) -> Section:
    bases = [ast.unparse(b) for b in node.bases]
    base_str = f"({', '.join(bases)})" if bases else ""
    class_sig = f"class {node.name}{base_str}"
    doc = ast.get_docstring(node) or ""
    lines = [f"# `{class_sig}`", ""]
    if doc:
        lines.extend((doc.strip(), ""))

    # Typed attributes (e.g. dataclass or class-level annotated attributes)
    attributes: list[str] = []
    for item in node.body:
        if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
            val_str = f" = {ast.unparse(item.value)}" if item.value else ""
            attributes.append(f"- `{item.target.id}: {ast.unparse(item.annotation)}{val_str}`")
    if attributes:
        lines.extend(("## Attributes", "", *attributes, ""))

    # Methods
    methods: list[str] = []
    for item in node.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            method_sig = _format_py_function_signature(item, is_method=True)
            method_doc = ast.get_docstring(item) or ""
            methods.append(f"### `{method_sig}`")
            if method_doc:
                methods.extend((method_doc.strip(), ""))
            else:
                methods.append("")
    if methods:
        lines.extend(("## Methods", "", *methods))

    content = "\n".join(lines).rstrip() + "\n"
    first_doc_line = doc.strip().splitlines()[0] if doc.strip() else f"Class {node.name}"
    return Section(
        id=f"py-{quote(rel_path, safe='')}-{node.name}",
        title=f"class {node.name}",
        path=f"{rel_path}:{node.name}",
        content=content,
        tokens=count_tokens(content, encoding_name=encoding_name),
        description=first_doc_line[:240],
        kind="code",
    )


def extract_python_sections(paths: list[Path], encoding_name: str = "cl100k_base") -> list[Section]:
    sections: list[Section] = []
    files: list[Path] = []
    for p in paths:
        if p.is_file() and p.suffix == ".py":
            files.append(p)
        elif p.is_dir():
            files.extend(sorted(p.rglob("*.py")))

    for file_path in files:
        try:
            tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
        except SyntaxError:
            continue

        rel = file_path.as_posix()
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not node.name.startswith("_"):
                    sections.append(_render_py_function(node, rel, encoding_name))
            elif isinstance(node, ast.ClassDef):
                if not node.name.startswith("_"):
                    sections.append(_render_py_class(node, rel, encoding_name))
    return sections


def extract_typescript_sections(paths: list[Path], encoding_name: str = "cl100k_base") -> list[Section]:
    sections: list[Section] = []
    files: list[Path] = []
    for p in paths:
        if p.is_file() and p.suffix in (".ts", ".tsx", ".d.ts"):
            files.append(p)
        elif p.is_dir():
            files.extend(sorted(p.rglob("*.ts")))
            files.extend(sorted(p.rglob("*.tsx")))

    for file_path in files:
        text = file_path.read_text(encoding="utf-8")
        rel = file_path.as_posix()

        # Match JSDoc + exported declaration blocks
        pattern = re.compile(
            r"(?:/\*\*(?P<jsdoc>[\s\S]*?)\*/\s*)?"
            r"export\s+(?:default\s+)?(?P<kind>interface|type|class|(?:async\s+)?function)\s+(?P<name>[A-Za-z0-9_$]+)"
            r"(?P<signature>[^;{]+)?"
            r"(?P<body>\{[\s\S]*?\n\}|=[^;]+;)?"
        )

        for match in pattern.finditer(text):
            jsdoc = match.group("jsdoc") or ""
            kind = match.group("kind")
            name = match.group("name")
            sig = (match.group("signature") or "").strip()
            body = (match.group("body") or "").strip()

            clean_doc_lines = []
            for d_line in jsdoc.strip().splitlines():
                d_line = re.sub(r"^\s*\*\s?", "", d_line).strip()
                if d_line:
                    clean_doc_lines.append(d_line)
            clean_doc = "\n".join(clean_doc_lines)

            lines = []
            if "function" in kind:
                full_sig = f"function {name}{sig}"
                lines.extend([f"# `{full_sig}`", ""])
                if clean_doc:
                    lines.extend((clean_doc, ""))
            elif kind == "interface":
                full_sig = f"interface {name}{sig}"
                lines.extend([f"# `{full_sig}`", ""])
                if clean_doc:
                    lines.extend((clean_doc, ""))
                if body:
                    lines.extend(["```typescript", f"interface {name}{sig} {body}", "```", ""])
            elif kind == "type":
                lines.extend([f"# `type {name}{sig}`", ""])
                if clean_doc:
                    lines.extend((clean_doc, ""))
                if body:
                    lines.extend(["```typescript", f"type {name}{sig} {body}", "```", ""])
            elif kind == "class":
                lines.extend([f"# `class {name}{sig}`", ""])
                if clean_doc:
                    lines.extend((clean_doc, ""))
                if body:
                    lines.extend(["```typescript", f"class {name}{sig} {body}", "```", ""])

            content = "\n".join(lines).rstrip() + "\n"
            first_doc = clean_doc_lines[0] if clean_doc_lines else f"{kind} {name}"
            sections.append(Section(
                id=f"ts-{quote(rel, safe='')}-{name}",
                title=f"{kind} {name}",
                path=f"{rel}:{name}",
                content=content,
                tokens=count_tokens(content, encoding_name=encoding_name),
                description=first_doc[:240],
                kind="code",
            ))
    return sections
