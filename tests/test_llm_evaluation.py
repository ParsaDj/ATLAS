import json
from pathlib import Path

import pytest

from apps.ai_agent.evaluation import evaluate_case, evaluate_dataset, load_cases


DATASET = Path("tests/evaluations/live_model_cases.json")


class EvidenceAwareClient:
    model = "frozen-test-model"

    def __init__(self, prohibited_claim=None):
        self.prohibited_claim = prohibited_claim

    def generate(self, prompt, schema):
        evidence = json.loads(prompt.split("EVIDENCE_JSON:\n", 1)[1])
        incident = evidence["incident"]
        mission = evidence["mission"]
        events = evidence["events"]
        documents = evidence["documents"]
        referenced = set(incident.get("event_ids", []))
        available = {event["event_id"] for event in events}
        missing = bool(referenced - available)
        classification = "unknown" if missing else incident["type"]
        confidence = (
            "insufficient"
            if missing
            else "limited"
            if incident["type"] == "disconnection"
            else "supported"
        )
        citations = [
            {"type": "event", "id": event["event_id"], "version": None, "sha256": None}
            for event in events
        ]
        citations.append(
            {"type": "mission", "id": mission["id"], "version": None, "sha256": None}
        )
        citations.extend(
            {
                "type": "document",
                "id": document["id"],
                "version": document["version"],
                "sha256": document["sha256"],
            }
            for document in documents
        )
        evidence_ids = [item["id"] for item in citations]
        return {
            "fault_classification": classification,
            "finding": self.prohibited_claim or "The supplied records support only the reported operational fault.",
            "confidence": confidence,
            "hypotheses": [
                {
                    "cause": "The underlying cause remains unconfirmed.",
                    "confidence": 0.5,
                    "evidence_ids": evidence_ids,
                }
            ],
            "missing_evidence": ["Root-cause observation"],
            "limitations": ["The records do not establish the underlying cause."],
            "recommended_next_step": documents[0]["approved_next_step"],
            "citations": citations,
        }


def test_frozen_dataset_is_versioned_and_nonempty():
    cases = load_cases(DATASET)
    assert len(cases) == 12
    assert len({case["id"] for case in cases}) == 12


def test_evaluation_reports_machine_scoreable_metrics():
    report = evaluate_dataset(DATASET, EvidenceAwareClient())
    assert report["schema_version"] == "atlas-live-model-evaluation-v1"
    assert report["dataset_cases"] == 12
    assert report["dataset_version"] == "2026-10-09"
    assert len(report["dataset_sha256"]) == 64
    assert set(report["metrics"].values()) == {1.0}
    assert all(len(case["observed"]["evidence_sha256"]) == 64 for case in report["cases"])


def test_prohibited_claim_phrase_is_reported_without_exposing_full_response():
    case = load_cases(DATASET)[0]
    phrase = case["expected"]["prohibited_claim_phrases"][0]
    result = evaluate_case(case, EvidenceAwareClient(phrase))
    assert result["checks"]["no_prohibited_claims"] is False
    assert result["observed"]["prohibited_claim_phrases"] == [phrase]
    assert "finding" not in result["observed"]


def test_dataset_loader_rejects_unknown_schema(tmp_path):
    path = tmp_path / "cases.json"
    path.write_text('{"schema_version":"unknown","cases":[]}')
    with pytest.raises(ValueError, match="schema"):
        load_cases(path)
