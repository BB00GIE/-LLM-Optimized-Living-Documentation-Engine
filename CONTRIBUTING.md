# Contributing to Living Documentation Engine

Thank you for your interest in contributing to the LLM-Optimized Living Documentation Engine! We welcome issues, suggestions, and pull requests.

## Development Setup

### Prerequisites

- Python 3.10, 3.11, or 3.12
- Git

### Installation

1. Fork the repository and clone your fork locally:
   ```bash
   git clone https://github.com/<your-username>/-LLM-Optimized-Living-Documentation-Engine.git
   cd -LLM-Optimized-Living-Documentation-Engine
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   # On Linux/macOS:
   source .venv/bin/activate
   # On Windows (PowerShell):
   .venv\Scripts\Activate.ps1
   ```

3. Install editable dependencies including development and test tooling:
   ```bash
   python -m pip install --upgrade pip
   python -m pip install -e ".[dev]"
   ```

## Running Tests & Verification

Before submitting a pull request, ensure all tests, lint checks, benchmarks, and conformance suites pass locally.

### 1. Test Suite
```bash
python -m pytest -v
```

### 2. Linting
```bash
python -m ruff check living_docs tests
```

### 3. Token Efficiency Benchmark
```bash
python -m living_docs benchmark
```

### 4. Agent Evaluation Harness
```bash
python -m living_docs eval
```

### 5. MCP Protocol Conformance
```bash
python -m living_docs conformance
```

### 6. Full Verification Suite (Optional)
```bash
python -m living_docs verify
```

## Pull Request Guidelines

1. **Branch Naming**: Use descriptive branch names like `feat/add-new-adapter` or `fix/ref-recursion-edge-case`.
2. **Atomic Commits**: Keep commits concise and write clear commit messages explaining *why* a change was made.
3. **Preserve Determinism**: Ensure schema parsing preserves required flags, parameter descriptions, and structural boundaries without arbitrary token truncation.
4. **CI Compliance**: All checks in `.github/workflows/ci.yml` (multi-OS testing across Linux, macOS, and Windows) must pass before merging.

## Code of Conduct

This project adheres to the Contributor Covenant Code of Conduct. By participating, you are expected to uphold this code. See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) for details.
