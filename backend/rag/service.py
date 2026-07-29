from .bm25_retriever import BM25Retriever
from .corpus_loader import CorpusLoader
from .models import RetrievalDecision


MIN_RELEVANCE_SCORE = 1.0
AMBIGUITY_SCORE_GAP = 0.5
MAX_RESULTS = 3


class CulturalRagService:
    retriever_version = "met-bm25-v1"

    def __init__(self, root="rag/corpus/met_open_access"):
        self.retriever = BM25Retriever(CorpusLoader(root).load())

    def query_for_brief(self, brief):
        direction = brief["visual_direction"]
        source = brief["cultural_source"]
        values = [
            brief["product_type"],
            source["name"],
            source.get("era"),
            source.get("creator"),
            direction["cultural_context"],
            direction["medium"],
            *brief["confirmed_facts"],
        ]
        return " ".join(value for value in values if value)

    def decide_query(self, query, top_k=MAX_RESULTS):
        candidates = tuple(self.retriever.search(query, top_k))
        qualified = tuple(item for item in candidates if item.score >= MIN_RELEVANCE_SCORE)
        if not qualified:
            return RetrievalDecision("no_match", "below_minimum_score_no_rag", query, (), candidates)
        if len(qualified) > 1 and qualified[0].score - qualified[1].score < AMBIGUITY_SCORE_GAP:
            return RetrievalDecision("no_match", "ambiguous_top_results_no_rag", query, (), candidates)
        return RetrievalDecision("matched", "reliable_match", query, qualified, candidates)

    def retrieve(self, brief, top_k=MAX_RESULTS):
        return self.decide_query(self.query_for_brief(brief), top_k)

    def evidence_block(self, decision):
        return [
            {"source_id": result.source_id, "title": result.title, "facts": result.evidence}
            for result in decision.results
        ]

    def verified_sources(self, decision, used_ids, evidence_status):
        available_ids = {result.source_id for result in decision.results}
        if (
            not isinstance(used_ids, list)
            or any(not isinstance(source_id, str) for source_id in used_ids)
            or len(used_ids) != len(set(used_ids))
            or not set(used_ids).issubset(available_ids)
            or evidence_status not in {
                "grounded",
                "insufficient_evidence",
                "creative_only",
            }
            or (evidence_status == "grounded" and not used_ids)
            or (evidence_status in {
                "insufficient_evidence",
                "creative_only",
            } and used_ids)

            or (not available_ids and evidence_status != "insufficient_evidence"
                and evidence_status != "creative_only")
        ):
            raise ValueError("MODEL_INVALID_CITATIONS")
        by_id = {result.source_id: result for result in decision.results}
        return [
            {
                "source_id": source_id,
                "title": by_id[source_id].title,
                "source_url": by_id[source_id].source_url,
                "license": by_id[source_id].license,
            }
            for source_id in used_ids
        ]
