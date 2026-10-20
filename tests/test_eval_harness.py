from pathlib import Path

from living_docs.eval_harness import evaluate_living_docs_engine


def test_agent_eval_harness_exceeds_accuracy_target(tmp_path):
    report = evaluate_living_docs_engine(
        output_dir=tmp_path / "out_eval",
        openapi_path=Path("examples/openapi.yaml"),
        python_src_path=Path("examples/src/client.py"),
        typescript_src_path=Path("examples/src/types.ts"),
    )

    # Spec Section 6.2 Target Criterion: ">90% first-pass accuracy on complex queries with zero invalid field name errors"
    assert report.total_tasks == 4
    assert report.passed_tasks == 4
    assert report.first_pass_accuracy >= 90.0
    assert report.first_pass_accuracy == 100.0

    for res in report.results:
        assert res.passed is True
        assert len(res.errors) == 0
        assert res.tokens_consumed < 1000
