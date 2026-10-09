# Performance benchmark

ATLAS includes a repeatable live-HTTP telemetry benchmark. It generates healthy
unassigned observations across the five synthetic robots and mixes exact
duplicate deliveries into the workload. Every request passes through bridge
authentication, input validation, the FastAPI route, a database transaction,
and the idempotency checks.

## Run with Docker Compose

```sh
docker compose up --build -d db api
docker compose --profile benchmark run --rm benchmark
```

Configure the workload through environment variables:

```sh
docker compose --profile benchmark run --rm \
  -e ATLAS_BENCHMARK_REQUESTS=5000 \
  -e ATLAS_BENCHMARK_CONCURRENCY=20 \
  -e ATLAS_BENCHMARK_DUPLICATE_FRACTION=0.1 \
  -e ATLAS_BENCHMARK_WARMUP=100 \
  benchmark
```

For a locally running API:

```sh
export ATLAS_TELEMETRY_API_KEY='the-key-configured-by-the-api'
python -m scripts.benchmark \
  --url http://127.0.0.1:8000 \
  --requests 1000 \
  --concurrency 10 \
  --duplicate-fraction 0.1 \
  --output benchmark-result.json
```

## Report contract

The JSON report records the schema and timestamp, target and workload,
execution environment, success and duplicate counts, total duration, requests
per second, and mean, p50, p95, p99, and maximum client-observed latency.

The command exits unsuccessfully if a request fails or if new and duplicate
responses differ from the generated workload. A fixed seed controls duplicate
selection and request order. Event IDs include a unique run identifier so
separate runs do not collide.

## Interpretation

This framework does not publish a performance claim by itself. A result is
meaningful only with its generated report, exact ATLAS revision, database
configuration, container limits, host hardware, and competing workloads.

The benchmark uses five robot rows, so PostgreSQL row-lock contention is part of
the measurement. It does not model hundreds of distinct robots, wide-area
networks, database replication, horizontal API scaling, physical reliability,
or long-term retention. Those properties must not be inferred from this test.
