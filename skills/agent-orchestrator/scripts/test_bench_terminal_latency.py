from scripts.bench_terminal_latency import run_benchmark


def test_benchmark_deterministic():
    a = run_benchmark(samples=25, seed=42)
    b = run_benchmark(samples=25, seed=42)
    assert a["p50_ms"] >= 0 and b["p50_ms"] >= 0
    assert a["p95_ok"] is True and b["p95_ok"] is True
    assert a["p99_ok"] is True and b["p99_ok"] is True
    # timing noise causes small numeric jitter; allow bounded difference after deterministic setup
    assert abs(a["p95_ms"] - b["p95_ms"]) < 0.5
    assert abs(a["p99_ms"] - b["p99_ms"]) < 0.5
    assert a["samples"] == 25


def test_benchmark_meets_issue77_threshold_target_after_seeded_run():
    report = run_benchmark(samples=200, seed=20260222)
    assert report["p95_ms"] <= 80.0
    assert report["p99_ms"] <= 150.0
    assert len(report["raw"]) == report["samples"]
