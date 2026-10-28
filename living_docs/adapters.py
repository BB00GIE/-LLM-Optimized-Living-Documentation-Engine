"""Adapters for popular documentation generators and frameworks.

This module provides lightweight adapters to discover, parse, and extract
documentation from common documentation setups:
- MkDocs (mkdocs.yml / docs_dir)
- Docusaurus (docusaurus.config.js / ts / docs/)
- Sphinx (conf.py / docs / source)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from living_docs.engine import Section


@dataclass(frozen=True)
class DocStackConfig:
    """Discovered documentation stack metadata."""
    stack: str  # 'mkdocs', 'docusaurus', 'sphinx', 'generic'
    root_path: Path
    docs_directories: list[Path]
    project_name: str | None = None
    nav: list[dict[str, Any]] | None = None


def detect_doc_stack(project_root: Path) -> DocStackConfig:
    """Detect the documentation framework configured in project_root.

    Inspects common configuration files:
    - `mkdocs.yml` or `mkdocs.yaml` for MkDocs
    - `docusaurus.config.js` or `docusaurus.config.ts` for Docusaurus
    - `conf.py` (e.g. docs/conf.py or conf.py) for Sphinx
    Falls back to 'generic' scanning for any `docs/` or `doc/` directories.
    """
    root = project_root.resolve()

    # 1. Check MkDocs
    for candidate in ("mkdocs.yml", "mkdocs.yaml"):
        mkdocs_file = root / candidate
        if mkdocs_file.is_file():
            return _parse_mkdocs_config(root, mkdocs_file)

    # 2. Check Docusaurus
    for candidate in ("docusaurus.config.js", "docusaurus.config.ts", "docusaurus.config.mjs"):
        docusaurus_file = root / candidate
        if docusaurus_file.is_file():
            return _parse_docusaurus_config(root, docusaurus_file)

    # 3. Check Sphinx
    sphinx_candidates = [
        root / "docs" / "conf.py",
        root / "doc" / "conf.py",
        root / "conf.py",
        root / "docs" / "source" / "conf.py",
    ]
    for conf_file in sphinx_candidates:
        if conf_file.is_file():
            return _parse_sphinx_config(root, conf_file)

    # 4. Fallback / Generic
    fallback_dirs = []
    for d in ("docs", "doc", "documentation"):
        target = root / d
        if target.is_dir():
            fallback_dirs.append(target)
    if not fallback_dirs:
        fallback_dirs = [root]

    return DocStackConfig(
        stack="generic",
        root_path=root,
        docs_directories=fallback_dirs,
        project_name=root.name,
    )


def _parse_mkdocs_config(root: Path, config_file: Path) -> DocStackConfig:
    """Parse mkdocs.yml to extract site_name, docs_dir, and nav."""
    try:
        content = yaml.safe_load(config_file.read_text(encoding="utf-8")) or {}
    except Exception:
        content = {}

    site_name = content.get("site_name")
    docs_dir_str = content.get("docs_dir", "docs")
    docs_dir = (root / docs_dir_str).resolve()
    if not docs_dir.is_dir():
        docs_dir = root / "docs"

    docs_directories = [docs_dir] if docs_dir.is_dir() else [root]
    nav = content.get("nav")

    return DocStackConfig(
        stack="mkdocs",
        root_path=root,
        docs_directories=docs_directories,
        project_name=site_name or root.name,
        nav=nav if isinstance(nav, list) else None,
    )


def _parse_docusaurus_config(root: Path, config_file: Path) -> DocStackConfig:
    """Extract project title and doc folders from a Docusaurus config."""
    text = ""
    try:
        text = config_file.read_text(encoding="utf-8")
    except Exception:
        pass

    # Simple heuristic to extract title from JS/TS config: title: 'My Site'
    title_match = re.search(r"""title:\s*['"`]([^'"`]+)['"`]""", text)
    project_name = title_match.group(1).strip() if title_match else root.name

    docs_dir = root / "docs"
    docs_directories = [docs_dir] if docs_dir.is_dir() else [root]

    return DocStackConfig(
        stack="docusaurus",
        root_path=root,
        docs_directories=docs_directories,
        project_name=project_name,
    )


def _parse_sphinx_config(root: Path, conf_file: Path) -> DocStackConfig:
    """Extract project name and source directory from Sphinx conf.py."""
    text = ""
    try:
        text = conf_file.read_text(encoding="utf-8")
    except Exception:
        pass

    project_match = re.search(r"""project\s*=\s*['"`]([^'"`]+)['"`]""", text)
    project_name = project_match.group(1).strip() if project_match else root.name

    docs_dir = conf_file.parent
    return DocStackConfig(
        stack="sphinx",
        root_path=root,
        docs_directories=[docs_dir],
        project_name=project_name,
    )


def extract_stack_sections(
    config: DocStackConfig,
    encoding_name: str = "cl100k_base",
) -> list[Section]:
    """Ingest markdown and documentation files based on the stack configuration."""
    from living_docs.engine import _markdown_sections

    sections = _markdown_sections(config.docs_directories, encoding_name=encoding_name)
    return sections
