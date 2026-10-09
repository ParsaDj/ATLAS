"""Measure ATLAS telemetry ingestion through a live HTTP deployment."""
from __future__ import annotations

import argparse
import json
import math
import os
import platform
import random
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx


SCHEMA_VERSION = "atlas-telemetry-benchmark-v1"


def percentile(values: list[float], quantile: float) -> float:
    """Return an interpolated percentile for a non-empty sample."""
    if not values:
        raise ValueError("percentile requires at least one value")
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def build_workload(
    request_count: int,
    duplicate_fraction: float,
    run_id: str,
    *,
    seed: int,
    occurred_at: str | None = None,
) -> list[dict]:
    if request_count < 1:
        raise ValueError("request_count must be positive")
    if not 0 <= duplicate_fraction < 1:
        raise ValueError("duplicate_fraction must be between 0 and 1")
    duplicate_count = int(request_count * duplicate_fraction)
    unique_count = request_count - duplicate_count
    timestamp = occurred_at or datetime.now(timezone.utc).isoformat()
    unique = [
        {
            "event_id": f"benchmark:{run_id}:{index}",
            "robot_id": f"robot-{index % 5 + 1}",
            "mission_id": None,
            "occurred_at": timestamp,
            "position": {"x": float(index % 100), "y": float(index % 5)},
            "battery": 80,
            "sensor_status": "ok",
            "mission_status": "running",
        }
        for index in range(unique_count)
    ]
    rng = random.Random(seed)
    duplicates = [dict(rng.choice(unique)) for _ in range(duplicate_count)]
    workload = unique + duplicates
    rng.shuffle(workload)
    return workload


def _send(url: str, bridge_key: str, payload: dict, timeout: float) -> dict:
    started = time.perf_counter()
    try:
        response = httpx.post(
            f"{url.rstrip('/')}/api/telemetry",
            headers={"X-ATLAS-Bridge-Key": bridge_key},
            json=payload,
            timeout=timeout,
        )
        latency_ms = (time.perf_counter() - started) * 1000
        body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        return {
            "status_code": response.status_code,
            "latency_ms": latency_ms,
            "duplicate": body.get("duplicate") if response.status_code == 200 else None,
            "event_id": payload["event_id"],
        }
    except httpx.HTTPError as error:
        return {
            "status_code": None,
            "latency_ms": (time.perf_counter() - started) * 1000,
            "duplicate": None,
            "event_id": payload["event_id"],
            "error": type(error).__name__,
        }


def summarize(results: list[dict], duration_seconds: float) -> dict:
    latencies = [result["latency_ms"] for result in results]
    successes = [result for result in results if result["status_code"] == 200]
    errors: dict[str, int] = {}
    for result in results:
        if result["status_code"] != 200:
            label = str(result.get("status_code") or result.get("error") or "unknown")
            errors[label] = errors.get(label, 0) + 1
    return {
        "requests": len(results),
        "successful": len(successes),
        "stored_new": sum(result["duplicate"] is False for result in successes),
        "accepted_duplicates": sum(result["duplicate"] is True for result in successes),
        "errors": errors,
        "duration_seconds": round(duration_seconds, 6),
        "requests_per_second": round(len(results) / duration_seconds, 3),
        "latency_ms": {
            "mean": round(statistics.fmean(latencies), 3),
            "p50": round(percentile(latencies, 0.50), 3),
            "p95": round(percentile(latencies, 0.95), 3),
            "p99": round(percentile(latencies, 0.99), 3),
            "max": round(max(latencies), 3),
        },
    }


def run_benchmark(
    *,
    url: str,
    bridge_key: str,
    request_count: int,
    concurrency: int,
    duplicate_fraction: float,
    warmup: int,
    timeout: float,
    seed: int,
) -> dict:
    if concurrency < 1:
        raise ValueError("concurrency must be positive")
    run_id = str(uuid4())
    if warmup:
        warmup_payloads = build_workload(warmup, 0, f"{run_id}:warmup", seed=seed)
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            warmup_results = list(
                pool.map(lambda payload: _send(url, bridge_key, payload, timeout), warmup_payloads)
            )
        if any(result["status_code"] != 200 for result in warmup_results):
            raise RuntimeError("benchmark warmup failed")

    payloads = build_workload(
        request_count, duplicate_fraction, run_id, seed=seed
    )
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        results = list(
            pool.map(lambda payload: _send(url, bridge_key, payload, timeout), payloads)
        )
    duration = time.perf_counter() - started
    summary = summarize(results, duration)
    expected_unique = len({payload["event_id"] for payload in payloads})
    summary["expected_unique"] = expected_unique
    if summary["successful"] != request_count:
        raise RuntimeError(f"benchmark had failed requests: {summary['errors']}")
    if summary["stored_new"] != expected_unique:
        raise RuntimeError("new-event count did not match the generated workload")
    if summary["accepted_duplicates"] != request_count - expected_unique:
        raise RuntimeError("duplicate count did not match the generated workload")

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target": url,
        "configuration": {
            "requests": request_count,
            "concurrency": concurrency,
            "duplicate_fraction": duplicate_fraction,
            "warmup_requests": warmup,
            "timeout_seconds": timeout,
            "seed": seed,
            "robots": 5,
            "payload": "unassigned healthy telemetry",
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "processor": platform.processor() or "unreported",
        },
        "results": summary,
        "limitations": [
            "This measures one client host against one ATLAS API deployment.",
            "It does not establish horizontal scalability or physical robot reliability.",
            "Results are comparable only when configuration and environment are reported together.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--bridge-key", default=os.getenv("ATLAS_TELEMETRY_API_KEY"))
    parser.add_argument("--requests", type=int, default=int(os.getenv("ATLAS_BENCHMARK_REQUESTS", "1000")))
    parser.add_argument("--concurrency", type=int, default=int(os.getenv("ATLAS_BENCHMARK_CONCURRENCY", "10")))
    parser.add_argument("--duplicate-fraction", type=float, default=float(os.getenv("ATLAS_BENCHMARK_DUPLICATE_FRACTION", "0.1")))
    parser.add_argument("--warmup", type=int, default=int(os.getenv("ATLAS_BENCHMARK_WARMUP", "50")))
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--seed", type=int, default=20261009)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.bridge_key:
        parser.error("set ATLAS_TELEMETRY_API_KEY or pass --bridge-key")
    try:
        report = run_benchmark(
            url=args.url,
            bridge_key=args.bridge_key,
            request_count=args.requests,
            concurrency=args.concurrency,
            duplicate_fraction=args.duplicate_fraction,
            warmup=args.warmup,
            timeout=args.timeout,
            seed=args.seed,
        )
    except (ValueError, RuntimeError) as error:
        raise SystemExit(f"ATLAS benchmark failed: {error}") from error
    output = json.dumps(report, indent=2)
    if args.output:
        args.output.write_text(output + "\n")
    print(output)


if __name__ == "__main__":
    main()
