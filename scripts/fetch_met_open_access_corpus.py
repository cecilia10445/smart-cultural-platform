#!/usr/bin/env python3
"""Freeze a small, auditable CC0 Met Open Access corpus; never downloads images."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

API = "https://collectionapi.metmuseum.org/public/collection/v1"
ROOT = Path("rag/corpus/met_open_access")
CATEGORIES = {
    "blue_white_porcelain": "Chinese blue and white porcelain",
    "landscape_painting": "Chinese landscape painting",
    "calligraphy": "Chinese calligraphy",
    "bronze_ritual_vessel": "Chinese bronze ritual vessel",
    "silk_textile": "Chinese silk textile",
    "buddhist_sculpture": "Chinese Buddha sculpture",
}
CURATED_SEED_OBJECT_IDS = {"calligraphy": [36003, 35993]}

def reject_or_accept(category, item):
    reasons = []
    fields = {key: item.get(key) for key in ("department", "culture", "country", "classification", "objectName", "medium", "title", "objectDate", "period", "dynasty", "objectURL")}
    if item.get("department") != "Asian Art": reasons.append("WRONG_DEPARTMENT")
    origin_values = [str(item.get(k) or "").lower() for k in ("culture", "country", "region", "geography")]
    origin = " ".join(origin_values)
    has_china = "china" in origin or "chinese" in origin
    if origin and not has_china: reasons.append("NON_CHINESE_ORIGIN")
    if not origin: reasons.append("ORIGIN_UNSPECIFIED")
    if not all(item.get(k) for k in ("objectID", "title", "objectName", "objectURL")): reasons.append("REQUIRED_FIELD_MISSING")
    if not any(item.get(k) for k in ("objectDate", "period", "dynasty")): reasons.append("REQUIRED_FIELD_MISSING")
    text = " ".join(str(item.get(k) or "") for k in ("classification", "objectName", "medium", "title", "culture")).lower()
    rules = {
        "blue_white_porcelain": ("porcelain", "ceramic", "blue-and-white"),
        "landscape_painting": ("painting", "landscape"), "calligraphy": ("calligraphy", "ink", "paper", "silk", "album leaf", "handscroll", "fan"),
        "bronze_ritual_vessel": ("bronze", "vessel", "ritual"), "silk_textile": ("silk", "textile", "tapestry", "garment"),
        "buddhist_sculpture": ("buddha", "buddhist", "sculpture"),
    }
    required = rules[category]
    if category == "landscape_painting": ok = "painting" in text and "landscape" in text
    elif category == "calligraphy":
        label = " ".join(str(item.get(k) or "") for k in ("title", "classification", "objectName")).lower()
        carrier = str(item.get("medium") or "").lower()
        ok = "calligraphy" in label and any(word in carrier for word in rules[category][1:])
    elif category == "bronze_ritual_vessel": ok = "bronze" in text and ("vessel" in text or "ritual" in text)
    elif category == "buddhist_sculpture": ok = "sculpture" in text and ("buddha" in text or "buddhist" in text)
    else: ok = sum(word in text for word in required) >= 2 if len(required) > 1 else required[0] in text
    if not ok: reasons.append("CATEGORY_MISMATCH")
    return not reasons, reasons, fields

def main():
    raw, docs = ROOT / "raw", ROOT / "documents"; raw.mkdir(parents=True, exist_ok=True); docs.mkdir(parents=True, exist_ok=True)
    session = requests.Session(); audit=[]; selected=[]; used=set()
    for category, query in CATEGORIES.items():
        search = session.get(f"{API}/search", params={"q": query, "departmentId": 6, "geoLocation": "China", "isPublicDomain": "true"}, timeout=(5,30)); search.raise_for_status()
        accepted=None
        candidates = [(object_id, "curated_seed") for object_id in CURATED_SEED_OBJECT_IDS.get(category, [])]
        candidates += [(object_id, "api_search") for object_id in (search.json().get("objectIDs") or [])[:50]]
        for object_id, discovery_method in candidates:
            response=session.get(f"{API}/objects/{object_id}", timeout=(5,30)); response.raise_for_status(); item=response.json()
            ok,reasons,fields=reject_or_accept(category,item)
            if object_id in used: ok=False; reasons.append("DUPLICATE_OBJECT")
            audit.append({"category":category,"object_id":object_id,"discovery_method":discovery_method,"accepted":ok,"rejection_reasons":reasons,"fields":fields})
            if ok: accepted=item; used.add(object_id); break
        if not accepted: raise RuntimeError(f"NO_ACCEPTED_OBJECT:{category}")
        blob=json.dumps(accepted,ensure_ascii=False,sort_keys=True,indent=2).encode(); digest=hashlib.sha256(blob).hexdigest()
        (raw/f"{accepted['objectID']}.json").write_bytes(blob)
        doc={"source_id":f"met-{accepted['objectID']}","category":category,"objectID":accepted['objectID'],"title":accepted['title'],"objectName":accepted['objectName'],"culture":accepted.get('culture'),"period":accepted.get('period'),"dynasty":accepted.get('dynasty'),"date":accepted.get('objectDate'),"medium":accepted.get('medium'),"dimensions":accepted.get('dimensions'),"classification":accepted.get('classification'),"department":accepted.get('department'),"objectURL":accepted['objectURL'],"source_url":f"{API}/objects/{accepted['objectID']}","license":"CC0-1.0","retrieved_at":datetime.now(timezone.utc).isoformat(),"source_sha256":digest,"retrieval_aliases":{"value":[],"provenance":"project_editorial_metadata"}}
        (docs/f"met-{accepted['objectID']}.json").write_text(json.dumps(doc,ensure_ascii=False,indent=2),encoding="utf-8"); selected.append(doc)
    (ROOT/"candidate_audit.json").write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding="utf-8")
    (ROOT/"manifest.json").write_text(json.dumps({"schema_version":"met-open-access-v1","license":"CC0-1.0","sources":[{"source_id":d['source_id'],"document":f"documents/{d['source_id']}.json","source_sha256":d['source_sha256']} for d in selected]},ensure_ascii=False,indent=2),encoding="utf-8")
if __name__ == "__main__": main()
