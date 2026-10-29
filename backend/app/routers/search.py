"""Smart search endpoint."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AccessLevel, SensitivityLevel, User
from app.routers.documents import to_document_out
from app.schemas import SearchIntent, SearchResponse, SearchResultItem
from app.security import get_current_user
from app.services.audit_service import log_access
from app.services.permission_service import get_access_level
from app.services.search_service import SearchFilters, search_documents

router = APIRouter(prefix="/api", tags=["Búsqueda inteligente"])


@router.get("/search", response_model=SearchResponse, summary="Búsqueda inteligente en documentos cifrados")
def search(
    request: Request,
    q: str = Query("", max_length=200, description="Texto a buscar (contenido, nombre, categoría, palabras clave)"),
    category: str | None = None,
    sensitivity: SensitivityLevel | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    owner_id: int | None = None,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    filters = SearchFilters(category, sensitivity, date_from, date_to, owner_id)
    outcome = search_documents(db, current_user, q, filters, limit)

    # The query itself is not logged: it may contain sensitive words.
    log_access(db, request, "search", user=current_user, detail=f"{len(outcome.results)} resultado{'' if len(outcome.results) == 1 else 's'}")

    return SearchResponse(
        query=q,
        total=len(outcome.results),
        intent=SearchIntent(category=outcome.intent_category, confidence=outcome.intent_confidence)
        if outcome.intent_category else None,
        results=[
            SearchResultItem(
                document=to_document_out(item.document, get_access_level(db, current_user, item.document) or AccessLevel.READ),
                score=item.score,
                reasons=item.reasons,
                matched_terms=item.matched_terms,
            )
            for item in outcome.results
        ],
    )
