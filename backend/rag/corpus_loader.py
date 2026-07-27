import hashlib
import json
from pathlib import Path


EXPECTED_SCHEMA_VERSION = "met-open-access-v1"
EXPECTED_LICENSE = "CC0-1.0"
EXPECTED_SOURCE_COUNT = 6
REQUIRED_DOCUMENT_FIELDS = {
    "source_id", "category", "title", "objectName", "objectURL", "source_url",
    "license", "source_sha256", "retrieval_aliases",
}


class CorpusUnavailable(RuntimeError):
    pass


class CorpusLoader:
    def __init__(self, root):
        self.root = Path(root)

    def _json_object(self, path):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise CorpusUnavailable("RAG_UNAVAILABLE") from error
        if not isinstance(value, dict):
            raise CorpusUnavailable("RAG_UNAVAILABLE")
        return value

    def load(self):
        manifest = self._json_object(self.root / "manifest.json")
        entries = manifest.get("sources")
        if (
            manifest.get("schema_version") != EXPECTED_SCHEMA_VERSION
            or manifest.get("license") != EXPECTED_LICENSE
            or not isinstance(entries, list)
            or len(entries) != EXPECTED_SOURCE_COUNT
        ):
            raise CorpusUnavailable("RAG_UNAVAILABLE")

        documents = []
        source_ids = set()
        categories = set()
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != {"source_id", "document", "source_sha256"}:
                raise CorpusUnavailable("RAG_UNAVAILABLE")
            source_id = entry.get("source_id")
            document_path = entry.get("document")
            expected_digest = entry.get("source_sha256")
            if (
                not isinstance(source_id, str)
                or not source_id.startswith("met-")
                or not source_id[4:].isdigit()
                or document_path != f"documents/{source_id}.json"
                or not isinstance(expected_digest, str)
                or not re_full_sha256(expected_digest)
            ):
                raise CorpusUnavailable("RAG_UNAVAILABLE")

            raw_path = self.root / "raw" / f"{source_id[4:]}.json"
            frozen_document_path = self.root / document_path
            if not raw_path.is_file() or not frozen_document_path.is_file():
                raise CorpusUnavailable("RAG_UNAVAILABLE")
            if hashlib.sha256(raw_path.read_bytes()).hexdigest() != expected_digest:
                raise CorpusUnavailable("RAG_UNAVAILABLE")

            document = self._json_object(frozen_document_path)
            aliases = document.get("retrieval_aliases")
            if (
                not REQUIRED_DOCUMENT_FIELDS.issubset(document)
                or document.get("source_id") != source_id
                or document.get("source_sha256") != expected_digest
                or source_id in source_ids
                or not isinstance(document.get("category"), str)
                or document["category"] in categories
                or document.get("license") != EXPECTED_LICENSE
                or not isinstance(document.get("source_url"), str)
                or not document["source_url"].startswith(
                    "https://collectionapi.metmuseum.org/public/collection/v1/objects/"
                )
                or not isinstance(document.get("objectURL"), str)
                or not document["objectURL"].startswith(
                    "https://www.metmuseum.org/art/collection/search/"
                )
                or not isinstance(aliases, dict)
                or aliases.get("provenance") != "project_editorial_metadata"
                or not isinstance(aliases.get("value"), list)
            ):
                raise CorpusUnavailable("RAG_UNAVAILABLE")
            source_ids.add(source_id)
            categories.add(document["category"])
            documents.append(document)
        return documents


def re_full_sha256(value):
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)
