import csv
import json
import sqlite3
from pathlib import Path

from living_docs.verification_suite import run_full_verification


def test_full_verification_suite_generates_data_and_exceeds_targets(tmp_path):
    results_dir = tmp_path / "verification_run"
    summary = run_full_verification(
        results_dir=results_dir,
        spec_path=Path("examples/posthog_production_spec.yaml"),
    )

    # 1. Overall verification targets
    assert summary["overall_success_rate"] == 100.0
    assert summary["total_experiments"] >= 10
    assert summary["passed_experiments"] == summary["total_experiments"]

    # 2. Token reduction targets (>60% reduction)
    token_stats = summary["token_reduction_stats"]
    assert token_stats["mean_pct"] > 60.0
    assert token_stats["median_pct"] > 60.0
    assert token_stats["total_tokens_saved"] > 1000

    # 3. Latency targets (sub-second performance)
    latency_stats = summary["latency_stats_ms"]
    assert latency_stats["p50"] < 1000.0
    assert latency_stats["p95"] < 2000.0

    # 4. Verify SQLite Database was created and populated
    db_file = Path(summary["database_file"])
    assert db_file.exists()
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM verification_runs WHERE status = 'PASS'")
    pass_count = cursor.fetchone()[0]
    assert pass_count == summary["total_experiments"]
    conn.close()

    # 5. Verify CSV and JSON outputs
    csv_file = Path(summary["csv_file"])
    assert csv_file.exists()
    with open(csv_file, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert len(rows) == summary["total_experiments"]
        assert all(row["status"] == "PASS" for row in rows)

    json_file = Path(summary["json_file"])
    assert json_file.exists()
    data = json.loads(json_file.read_text(encoding="utf-8"))
    assert len(data) == summary["total_experiments"]
