from rank_bm25 import BM25Okapi

from .models import RetrievalResult
from .tokenizer import tokenize


RETRIEVAL_ALIASES = {
    "blue_white_porcelain": "中国 青花瓷 青花 瓷器 陶瓷",
    "landscape_painting": "中国 山水画 水墨",
    "calligraphy": "中国 书法 扇面",
    "bronze_ritual_vessel": "中国 青铜 礼器 器皿",
    "silk_textile": "中国 丝织品 纺织",
    "buddhist_sculpture": "中国 佛教 佛像 造像",
}
INDEXED_OFFICIAL_FIELDS = (
    "title", "objectName", "culture", "period", "medium", "classification", "category",
)
EVIDENCE_FIELDS = (
    "objectName", "culture", "period", "dynasty", "date", "medium",
    "classification", "department",
)


class BM25Retriever:
    def __init__(self, documents):
        self.documents = tuple(documents)
        indexed_documents = []
        for document in self.documents:
            official_text = " ".join(str(document.get(key) or "") for key in INDEXED_OFFICIAL_FIELDS)
            indexed_documents.append(tokenize(f"{official_text} {RETRIEVAL_ALIASES[document['category']]}"))
        self.index = BM25Okapi(indexed_documents)

    def search(self, query, top_k=3):
        if not isinstance(top_k, int) or not 1 <= top_k <= 3:
            raise ValueError("INVALID_TOP_K")
        query_tokens = tokenize(query)
        if not query_tokens:
            return []
        scores = self.index.get_scores(query_tokens)
        ranked = sorted(enumerate(scores), key=lambda item: item[1], reverse=True)[:top_k]
        return [
            RetrievalResult(
                source_id=self.documents[index]["source_id"],
                score=float(score),
                title=self.documents[index]["title"],
                source_url=self.documents[index]["objectURL"],
                license=self.documents[index]["license"],
                evidence={
                    key: self.documents[index].get(key)
                    for key in EVIDENCE_FIELDS
                    if self.documents[index].get(key)
                },
            )
            for index, score in ranked
            if score > 0
        ]
