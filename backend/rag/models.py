from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class RetrievalResult:
    source_id: str
    score: float
    title: str
    source_url: str
    license: str
    evidence: dict


@dataclass(frozen=True)
class RetrievalDecision:
    status: str
    reason: str
    query: str
    results: Tuple[RetrievalResult, ...]
    candidates: Tuple[RetrievalResult, ...]
