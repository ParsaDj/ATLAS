"""Run the optional ATLAS investigator against the frozen evaluation dataset."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from apps.ai_agent.evaluation import evaluate_dataset
from apps.ai_agent.llm import OpenAICompatibleClient


DEFAULT_DATASET = Path("tests/evaluations/live_model_cases.json")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default=os.getenv("ATLAS_LLM_MODEL"))
    parser.add_argument("--api-key", default=os.getenv("ATLAS_LLM_API_KEY"))
    parser.add_argument(
        "--base-url",
        default=os.getenv("ATLAS_LLM_BASE_URL", "https://api.openai.com/v1"),
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.getenv("ATLAS_LLM_TIMEOUT_SECONDS", "30")),
    )
    args = parser.parse_args()
    if not args.model:
        parser.error("set ATLAS_LLM_MODEL or pass --model")
    if not args.api_key:
        parser.error("set ATLAS_LLM_API_KEY or pass --api-key")

    report = evaluate_dataset(
        args.dataset,
        OpenAICompatibleClient(
            api_key=args.api_key,
            model=args.model,
            base_url=args.base_url,
            timeout=args.timeout,
        ),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report["metrics"], indent=2))


if __name__ == "__main__":
    main()
