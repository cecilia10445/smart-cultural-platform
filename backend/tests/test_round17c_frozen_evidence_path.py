from pathlib import Path

from evaluation.round17c_runner import BRIEF_PAYLOAD, freeze_evidence


def test_default_frozen_evidence_uses_repository_rag_corpus_without_model_calls():
    corpus = Path(__file__).resolve().parents[2] / "rag" / "corpus" / "met_open_access"
    assert corpus.is_dir()
    frozen = freeze_evidence(BRIEF_PAYLOAD["brief"])
    assert frozen["status"] == "grounded"
    assert frozen["sources"]
    assert "met-65625" in {item["source_id"] for item in frozen["sources"]}
