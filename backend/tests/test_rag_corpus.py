import hashlib
import json
import shutil
from pathlib import Path

import pytest

from backend.rag.bm25_retriever import BM25Retriever
from backend.rag.corpus_loader import CorpusLoader, CorpusUnavailable
from backend.rag.service import CulturalRagService


CORPUS_ROOT = "rag/corpus/met_open_access"
KNOWN_QUERIES = {
    "中国青花瓷文创书签": "met-39666",
    "中国山水画水墨": "met-65625",
    "明代书法扇面": "met-36003",
    "中国青铜礼器器皿": "met-76974",
    "中国丝织品纺织纹样": "met-51486",
    "唐代佛教造像佛像": "met-61549",
}


def copy_corpus(tmp_path):
    target = tmp_path / "corpus"
    shutil.copytree(CORPUS_ROOT, target)
    return target


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def test_frozen_met_corpus_is_complete_and_traceable():
    documents = CorpusLoader(CORPUS_ROOT).load()
    assert len(documents) == 6
    assert len({document["source_id"] for document in documents}) == 6
    assert len({document["category"] for document in documents}) == 6
    assert all(document["license"] == "CC0-1.0" for document in documents)
    assert all(
        document["retrieval_aliases"]["provenance"] == "project_editorial_metadata"
        for document in documents
    )
    for document in documents:
        raw_path = Path(CORPUS_ROOT) / "raw" / f"{document['objectID']}.json"
        assert hashlib.sha256(raw_path.read_bytes()).hexdigest() == document["source_sha256"]


@pytest.mark.parametrize(("query", "source_id"), KNOWN_QUERIES.items())
def test_six_known_categories_and_compound_porcelain_term_retrieve_at_top_one(query, source_id):
    retriever = BM25Retriever(CorpusLoader(CORPUS_ROOT).load())
    assert retriever.search(query)[0].source_id == source_id


def test_no_match_and_cross_category_ambiguity_are_conservative():
    service = CulturalRagService(CORPUS_ROOT)
    assert service.decide_query("现代汽车发动机").status == "no_match"
    ambiguous = service.decide_query("中国传统艺术文创")
    assert ambiguous.status == "no_match"
    assert ambiguous.reason == "below_minimum_score_no_rag"
    assert [round(item.score, 3) for item in ambiguous.candidates] == [0.318, 0.3, 0.269]
    strong_ambiguity = service.decide_query("青花瓷 山水画")
    assert strong_ambiguity.status == "no_match"
    assert strong_ambiguity.reason == "ambiguous_top_results_no_rag"
    assert strong_ambiguity.results == ()


@pytest.mark.parametrize("mutation", ["missing", "invalid-json", "invalid-shape"])
def test_manifest_missing_or_malformed_is_stable(tmp_path, mutation):
    root = copy_corpus(tmp_path)
    manifest_path = root / "manifest.json"
    if mutation == "missing":
        manifest_path.unlink()
    elif mutation == "invalid-json":
        manifest_path.write_text("{", encoding="utf-8")
    else:
        write_json(manifest_path, [])
    with pytest.raises(CorpusUnavailable, match="RAG_UNAVAILABLE"):
        CorpusLoader(root).load()


def test_raw_sha256_mismatch_is_rejected(tmp_path):
    root = copy_corpus(tmp_path)
    (root / "raw" / "39666.json").write_text("{}", encoding="utf-8")
    with pytest.raises(CorpusUnavailable, match="RAG_UNAVAILABLE"):
        CorpusLoader(root).load()


def test_duplicate_source_id_is_rejected(tmp_path):
    root = copy_corpus(tmp_path)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["sources"][1] = dict(manifest["sources"][0])
    write_json(manifest_path, manifest)
    with pytest.raises(CorpusUnavailable, match="RAG_UNAVAILABLE"):
        CorpusLoader(root).load()


@pytest.mark.parametrize("relative_path", ["documents/met-39666.json", "raw/39666.json"])
def test_missing_document_or_raw_file_is_rejected(tmp_path, relative_path):
    root = copy_corpus(tmp_path)
    (root / relative_path).unlink()
    with pytest.raises(CorpusUnavailable, match="RAG_UNAVAILABLE"):
        CorpusLoader(root).load()


def test_runtime_retrieval_does_not_access_met_api(monkeypatch):
    monkeypatch.setattr(
        "requests.sessions.Session.request",
        lambda *_args, **_kwargs: pytest.fail("runtime retrieval must remain local"),
    )
    assert CulturalRagService(CORPUS_ROOT).decide_query("青花瓷").status == "matched"


def test_retrieval_aliases_never_enter_evidence_block():
    service = CulturalRagService(CORPUS_ROOT)
    decision = service.decide_query("中国青花瓷文创书签")
    rendered = json.dumps(service.evidence_block(decision), ensure_ascii=False)
    assert "retrieval_aliases" not in rendered
    assert "project_editorial_metadata" not in rendered
    assert "source_id" in rendered


def test_used_source_ids_must_be_a_valid_subset_and_match_status():
    service = CulturalRagService(CORPUS_ROOT)
    decision = service.decide_query("中国青花瓷文创书签")
    sources = service.verified_sources(decision, ["met-39666"], "grounded")
    assert sources == [{
        "source_id": "met-39666",
        "title": "Jar with dragon",
        "source_url": "https://www.metmuseum.org/art/collection/search/39666",
        "license": "CC0-1.0",
    }]
    with pytest.raises(ValueError, match="MODEL_INVALID_CITATIONS"):
        service.verified_sources(decision, ["met-not-retrieved"], "grounded")
    with pytest.raises(ValueError, match="MODEL_INVALID_CITATIONS"):
        service.verified_sources(decision, [], "grounded")


def test_no_evidence_only_accepts_insufficient_evidence():
    service = CulturalRagService(CORPUS_ROOT)
    decision = service.decide_query("现代汽车发动机")
    assert service.verified_sources(decision, [], "insufficient_evidence") == []
    with pytest.raises(ValueError, match="MODEL_INVALID_CITATIONS"):
        service.verified_sources(decision, ["met-39666"], "grounded")
