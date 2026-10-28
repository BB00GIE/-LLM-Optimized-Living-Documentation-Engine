from pathlib import Path
from living_docs.adapters import detect_doc_stack, extract_stack_sections
from living_docs.engine import build_artifacts


def test_detect_mkdocs_stack(tmp_path):
    mkdocs_yml = tmp_path / "mkdocs.yml"
    mkdocs_yml.write_text(
        """site_name: "My Awesome Tool"
docs_dir: "my_docs"
nav:
  - Home: index.md
  - Guide: guide.md
""",
        encoding="utf-8",
    )
    docs_dir = tmp_path / "my_docs"
    docs_dir.mkdir()
    (docs_dir / "index.md").write_text("# Home\nWelcome to my tool.", encoding="utf-8")
    (docs_dir / "guide.md").write_text("# Guide\nHow to use it.", encoding="utf-8")

    config = detect_doc_stack(tmp_path)
    assert config.stack == "mkdocs"
    assert config.project_name == "My Awesome Tool"
    assert config.docs_directories == [docs_dir]

    sections = extract_stack_sections(config)
    assert len(sections) == 2
    titles = {s.title for s in sections}
    assert "Home" in titles
    assert "Guide" in titles


def test_detect_docusaurus_stack(tmp_path):
    docusaurus_config = tmp_path / "docusaurus.config.js"
    docusaurus_config.write_text(
        """module.exports = {
  title: 'My Docusaurus Site',
  tagline: 'Dinosaurs are cool',
  url: 'https://your-docusaurus-site.example.com',
};
""",
        encoding="utf-8",
    )
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "intro.mdx").write_text(
        """---
sidebar_position: 1
---
import Highlight from '@site/src/components/Highlight';

# Tutorial Intro

Let's discover Docusaurus in less than 5 minutes.
""",
        encoding="utf-8",
    )

    config = detect_doc_stack(tmp_path)
    assert config.stack == "docusaurus"
    assert config.project_name == "My Docusaurus Site"
    assert config.docs_directories == [docs_dir]

    sections = extract_stack_sections(config)
    assert len(sections) == 1
    assert sections[0].title == "Tutorial Intro"
    assert "import Highlight" not in sections[0].content


def test_detect_sphinx_stack(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    conf_py = docs_dir / "conf.py"
    conf_py.write_text(
        """# Configuration file for the Sphinx documentation builder.
project = 'Sphinx Test Project'
copyright = '2026, Brandon'
author = 'Brandon'
""",
        encoding="utf-8",
    )
    (docs_dir / "index.md").write_text("# Welcome to Sphinx Docs\nSome sphinx markdown content.", encoding="utf-8")

    config = detect_doc_stack(tmp_path)
    assert config.stack == "sphinx"
    assert config.project_name == "Sphinx Test Project"
    assert config.docs_directories == [docs_dir]

    sections = extract_stack_sections(config)
    assert len(sections) == 1
    assert sections[0].title == "Welcome to Sphinx Docs"


def test_build_artifacts_with_doc_stack_root(tmp_path):
    stack_dir = tmp_path / "site"
    stack_dir.mkdir()
    (stack_dir / "mkdocs.yml").write_text("site_name: Auto Detected Site\n", encoding="utf-8")
    docs_dir = stack_dir / "docs"
    docs_dir.mkdir()
    (docs_dir / "page.md").write_text("# Auto Page\nSome content for living docs.", encoding="utf-8")

    out_dir = tmp_path / "out"
    manifest = build_artifacts(
        output_directory=out_dir,
        doc_stack_root=stack_dir,
    )
    assert manifest["project"] == "Auto Detected Site"
    assert len(manifest["sections"]) == 1
    assert manifest["sections"][0]["title"] == "Auto Page"
    assert (out_dir / "llms.txt").exists()
    assert (out_dir / "docs-index.json").exists()
