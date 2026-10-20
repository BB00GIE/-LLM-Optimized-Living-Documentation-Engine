"""Machine-optimized documentation generation and retrieval."""

from living_docs.ast_parser import extract_python_sections, extract_typescript_sections
from living_docs.embeddings import Embedder, HashingEmbedder, cosine_similarity
from living_docs.engine import DocumentationEngine, build_artifacts, count_tokens

__all__ = [
    "DocumentationEngine",
    "build_artifacts",
    "count_tokens",
    "Embedder",
    "HashingEmbedder",
    "cosine_similarity",
    "extract_python_sections",
    "extract_typescript_sections",
]

