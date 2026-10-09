from scripts.benchmark import build_workload, percentile, summarize


def test_workload_has_reproducible_exact_duplicates():
    timestamp = "2026-10-09T12:00:00+00:00"
    first = build_workload(100, 0.2, "run", seed=17, occurred_at=timestamp)
    second = build_workload(100, 0.2, "run", seed=17, occurred_at=timestamp)
    assert first == second
    assert len(first) == 100
    assert len({event["event_id"] for event in first}) == 80
    grouped = {}
    for event in first:
        grouped.setdefault(event["event_id"], []).append(event)
    assert all(events[0] == event for events in grouped.values() for event in events)


def test_percentiles_and_summary_are_calculated_from_measured_samples():
    results = [
        {"status_code": 200, "latency_ms": value, "duplicate": value == 40}
        for value in (10, 20, 30, 40)
    ]
    summary = summarize(results, 2)
    assert percentile([10, 20, 30, 40], 0.50) == 25
    assert summary["requests_per_second"] == 2
    assert summary["stored_new"] == 3
    assert summary["accepted_duplicates"] == 1
    assert summary["latency_ms"] == {
        "mean": 25.0,
        "p50": 25.0,
        "p95": 38.5,
        "p99": 39.7,
        "max": 40,
    }
