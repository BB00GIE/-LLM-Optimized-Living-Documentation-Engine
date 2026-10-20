from living_docs.benchmark import run_token_efficiency_benchmark


def test_token_efficiency_benchmark_exceeds_sixty_percent_target():
    results = run_token_efficiency_benchmark(encoding_name="cl100k_base")
    assert len(results) == 2

    html_result = results[0]
    assert html_result.schema_preserved is True
    # Spec section 6.1 requires: ">60% reduction in token consumption"
    assert html_result.reduction_percentage > 60.0
    assert html_result.reduction_percentage >= 90.0

    openapi_result = results[1]
    assert openapi_result.schema_preserved is True
    assert openapi_result.reduction_percentage > 60.0


def test_token_efficiency_benchmark_with_o200k():
    results = run_token_efficiency_benchmark(encoding_name="o200k_base")
    html_result = results[0]
    assert html_result.schema_preserved is True
    assert html_result.reduction_percentage > 60.0

    openapi_result = results[1]
    assert openapi_result.schema_preserved is True
    assert openapi_result.reduction_percentage >= 55.0


def test_token_efficiency_benchmark_with_custom_files(tmp_path):
    from pathlib import Path

    custom_html = tmp_path / "custom.html"
    custom_html.write_text("<html><body>" + "<p>Verbose narrative page description.</p>" * 50 + "</body></html>", encoding="utf-8")

    results = run_token_efficiency_benchmark(
        custom_html_path=custom_html,
        custom_openapi_path=Path("examples/openapi.yaml"),
    )
    assert len(results) == 2
    for r in results:
        assert r.schema_preserved is True
        assert r.reduction_percentage > 60.0


def test_benchmark_handles_path_level_metadata_and_empty_spec(tmp_path):
    import pytest
    from pathlib import Path

    # Spec where 'summary' and 'parameters' appear before 'get'
    spec_with_meta = tmp_path / "meta_spec.json"
    spec_with_meta.write_text(
        '{"openapi":"3.0.0","info":{"title":"T","version":"1"},"paths":{"/items":{"summary":"Items","parameters":[],"get":{"summary":"List items","responses":{"200":{"description":"OK"}}}}}}',
        encoding="utf-8",
    )
    res = run_token_efficiency_benchmark(custom_openapi_path=spec_with_meta)
    assert len(res) == 2
    assert "GET /items" in res[0].scenario

    # Empty spec with no operations raises ValueError
    empty_spec = tmp_path / "empty_spec.json"
    empty_spec.write_text('{"openapi":"3.0.0","info":{"title":"E","version":"1"},"paths":{}}', encoding="utf-8")
    with pytest.raises(ValueError, match="No valid HTTP operations found"):
        run_token_efficiency_benchmark(custom_openapi_path=empty_spec)


def test_benchmark_raises_filenotfound_on_missing_custom_files():
    import pytest
    from pathlib import Path

    with pytest.raises(FileNotFoundError, match="HTML documentation file not found"):
        run_token_efficiency_benchmark(custom_html_path=Path("non_existent_file.html"))

    with pytest.raises(FileNotFoundError, match="OpenAPI specification file not found"):
        run_token_efficiency_benchmark(custom_openapi_path=Path("non_existent_file.yaml"))
