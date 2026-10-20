"""Machine-optimized documentation generation and retrieval."""

from living_docs.embeddings import Embedder, HashingEmbedder, cosine_similarity
from living_docs.engine import DocumentationEngine, build_artifacts, count_tokens

__all__ = [
    "DocumentationEngine",
    "build_artifacts",
    "count_tokens",
    "Embedder",
    "HashingEmbedder",
    "cosine_similarity",
]

