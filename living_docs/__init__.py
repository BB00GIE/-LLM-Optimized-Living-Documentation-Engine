"""Machine-optimized documentation generation and retrieval."""

from living_docs.adapters import DocStackConfig, detect_doc_stack, extract_stack_sections
from living_docs.ast_parser import extract_python_sections, extract_typescript_sections
from living_docs.benchmark import run_token_efficiency_benchmark
from living_docs.conformance import run_mcp_conformance_suite
from living_docs.embeddings import Embedder, HashingEmbedder, cosine_similarity
from living_docs.engine import DocumentationEngine, build_artifacts, count_tokens
from living_docs.eval_harness import evaluate_living_docs_engine
from living_docs.stubs import export_client_stubs, generate_python_stubs, generate_typescript_stubs
from living_docs.verification_suite import VerificationDatabase, run_full_verification

__all__ = [
    "DocStackConfig",
    "detect_doc_stack",
    "extract_stack_sections",
    "DocumentationEngine",
    "build_artifacts",
    "count_tokens",
    "Embedder",
    "HashingEmbedder",
    "cosine_similarity",
    "extract_python_sections",
    "extract_typescript_sections",
    "run_token_efficiency_benchmark",
    "evaluate_living_docs_engine",
    "run_mcp_conformance_suite",
    "run_full_verification",
    "VerificationDatabase",
    "export_client_stubs",
    "generate_python_stubs",
    "generate_typescript_stubs",
]

