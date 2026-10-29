"""Smart search over encrypted documents.

Three signals are combined into a relevance score (0-1):
  1. Content  (55 %): query words found in the document's blind index (search inside the encrypted file).
  2. Metadata (35 %): words found in file name, category, keywords or sensitive-data labels,
                      with typo tolerance (fuzzy matching).
  3. AI intent(10 %): the classifier guesses which category the query is about and boosts those
                      documents; with a confident intent, documents of that category are suggested
                      even when no word matches ("semantic" results).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from difflib import SequenceMatcher


from sqlalchemy.orm import Session, undefer

from app.ai.classifier import get_classifier
from app.ai.search_index import blind_token, extract_stems
from app.models import Document, SensitivityLevel, User
from app.services.permission_service import accessible_documents_query

CONTENT_WEIGHT = 0.55
METADATA_WEIGHT = 0.35
INTENT_WEIGHT = 0.10
FUZZY_THRESHOLD = 0.82
INTENT_MIN_CONFIDENCE = 0.25
INTENT_MIN_MARGIN = 0.08
SEMANTIC_ONLY_SCORE_CAP = 0.30  # results found only by intent never outrank real word matches


@dataclass
class SearchFilters:
    category: str | None = None
    sensitivity: SensitivityLevel | None = None
    date_from: date | None = None
    date_to: date | None = None
    owner_id: int | None = None


@dataclass
class ScoredDocument:
    document: Document
    score: float
    reasons: list[str] = field(default_factory=list)
    matched_terms: list[str] = field(default_factory=list)


@dataclass
class SearchOutcome:
    intent_category: str | None
    intent_confidence: float
    results: list[ScoredDocument]


def _detect_intent(query: str) -> tuple[str | None, float]:
    scores = list(get_classifier().query_intent(query).items())
    if len(scores) < 2:
        return None, 0.0
    (best_label, best), (_, second) = scores[0], scores[1]
    if best >= INTENT_MIN_CONFIDENCE and best - second >= INTENT_MIN_MARGIN:
        return best_label, best
    return None, best


def _metadata_stems(document: Document) -> set[str]:
    finding_labels = " ".join(f.get("label", "") for f in (document.sensitive_findings or {}).values())
    text = " ".join([document.original_name.replace("_", " ").replace("-", " "), document.category,
                     " ".join(document.keywords or []), finding_labels])
    return set(extract_stems(text))


def _fuzzy_in(term: str, candidates: set[str]) -> bool:
    if term in candidates:
        return True
    return any(
        abs(len(term) - len(candidate)) <= 2 and SequenceMatcher(None, term, candidate).ratio() >= FUZZY_THRESHOLD
        for candidate in candidates
    )


def _apply_filters(query, filters: SearchFilters):
    if filters.category:
        query = query.where(Document.category == filters.category)
    if filters.sensitivity:
        query = query.where(Document.sensitivity == filters.sensitivity)
    if filters.owner_id:
        query = query.where(Document.owner_id == filters.owner_id)
    if filters.date_from:
        query = query.where(Document.uploaded_at >= datetime.combine(filters.date_from, time.min, timezone.utc))
    if filters.date_to:
        query = query.where(Document.uploaded_at <= datetime.combine(filters.date_to, time.max, timezone.utc))
    return query


def search_documents(db: Session, user: User, text: str, filters: SearchFilters, limit: int = 50) -> SearchOutcome:
    query = _apply_filters(accessible_documents_query(user), filters).options(undefer(Document.search_index))
    documents = list(db.scalars(query).all())

    text = text.strip()
    if not text:
        return SearchOutcome(None, 0.0, [ScoredDocument(d, 0.0, ["Coincide con los filtros"]) for d in documents[:limit]])

    # Keep the user's original words to show which ones matched; map each to its stem and blind token.
    query_words = list(dict.fromkeys(w for w in text.split() if extract_stems(w)))
    word_stems = {word: extract_stems(word)[0] for word in query_words}
    word_tokens = {word: blind_token(s) for word, s in word_stems.items()}
    intent_category, intent_confidence = _detect_intent(text)

    results: list[ScoredDocument] = []
    for document in documents:
        index = set(document.search_index or [])
        metadata = _metadata_stems(document)

        content_hits = [word for word in query_words if word_tokens[word] in index]
        metadata_hits = [word for word in query_words if _fuzzy_in(word_stems[word], metadata)]
        total_words = max(len(query_words), 1)
        content_ratio = len(content_hits) / total_words
        metadata_ratio = len(metadata_hits) / total_words
        intent_match = intent_category is not None and document.category == intent_category

        if not content_hits and not metadata_hits and not intent_match:
            continue

        score = CONTENT_WEIGHT * content_ratio + METADATA_WEIGHT * metadata_ratio
        reasons = []
        if content_hits:
            noun = "término" if total_words == 1 else "términos"
            reasons.append(f"El contenido cifrado contiene {len(content_hits)} de {total_words} {noun}")
        if metadata_hits:
            reasons.append("Coincide en nombre, categoría o palabras clave")
        if intent_match:
            score += INTENT_WEIGHT * intent_confidence / max(intent_confidence, 0.5)
            reasons.append(f"La IA relaciona la búsqueda con {intent_category}")
            if not content_hits and not metadata_hits:
                score = min(score, SEMANTIC_ONLY_SCORE_CAP)

        matched = list(dict.fromkeys(content_hits + metadata_hits))
        results.append(ScoredDocument(document, round(min(score, 1.0), 3), reasons, matched))

    results.sort(key=lambda r: (r.score, r.document.uploaded_at), reverse=True)
    return SearchOutcome(intent_category, intent_confidence, results[:limit])
