import asyncio
from pathlib import Path

from living_docs.conformance import run_mcp_conformance_suite
from living_docs.engine import build_artifacts


def test_mcp_protocol_conformance_suite(tmp_path):
    output_dir = tmp_path / "out_conformance"
    build_artifacts(
        output_directory=output_dir,
        openapi_files=[Path("examples/openapi.yaml")],
    )

    report = asyncio.run(run_mcp_conformance_suite(output_dir / "docs-index.json"))

    assert report.total_checks >= 5
    assert report.all_passed is True
    assert report.passed_checks == report.total_checks

    check_names = {c.name for c in report.checks}
    assert "resource_registration_docs_manifest" in check_names
    assert "resource_read_manifest_schema" in check_names
    assert "tools_registration_conformance" in check_names
    assert "tool_call_get_api_spec_success" in check_names
    assert "tool_call_error_contract_conformance" in check_names
    assert "tool_call_search_docs_token_budget" in check_names
