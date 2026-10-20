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
