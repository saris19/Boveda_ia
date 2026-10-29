"""Dashboard statistics, scoped to what the current user is allowed to see."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AccessLog, Document, Role, SensitivityLevel, User
from app.schemas import AccessLogOut, CountItem, DayActivity, StatsResponse
from app.security import get_current_user
from app.services.permission_service import accessible_documents_query

router = APIRouter(prefix="/api", tags=["Panel"])

ACTIVITY_DAYS = 14
SENSITIVITY_ORDER = [level.value for level in SensitivityLevel]


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


@router.get("/stats", response_model=StatsResponse, summary="Indicadores del panel")
def stats(
    tz_offset: int = Query(0, ge=-840, le=840, description="Minutos a sumar a UTC para la hora local (Colombia: -300)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    local_zone = timezone(timedelta(minutes=tz_offset))

    def _day(value: datetime) -> str:
        return _as_utc(value).astimezone(local_zone).date().isoformat()

    documents = list(db.scalars(accessible_documents_query(current_user)).all())
    indexed_ids = set(
        db.scalars(
            accessible_documents_query(current_user)
            .with_only_columns(Document.id)
            .where(Document.search_index.is_not(None))
        ).all()
    )

    by_category = Counter(d.category for d in documents)
    by_sensitivity = Counter(d.sensitivity.value for d in documents)
    findings = Counter()
    for document in documents:
        for finding in (document.sensitive_findings or {}).values():
            findings[finding.get("label", "?")] += 1

    now = datetime.now(timezone.utc)
    today_local = now.astimezone(local_zone).date()
    first_day = today_local - timedelta(days=ACTIVITY_DAYS - 1)
    days = [(first_day + timedelta(days=i)).isoformat() for i in range(ACTIVITY_DAYS)]
    since = datetime.combine(first_day, datetime.min.time(), local_zone).astimezone(timezone.utc)
    activity = {day: DayActivity(date=day) for day in days}
    for document in documents:
        day = _day(document.uploaded_at)
        if day in activity:
            activity[day].uploads += 1

    is_admin = current_user.role == Role.ADMIN
    logs_query = select(AccessLog).where(AccessLog.timestamp >= since)
    if not is_admin:
        logs_query = logs_query.where(AccessLog.user_id == current_user.id)
    logs = list(db.scalars(logs_query).all())
    for log in logs:
        day = _day(log.timestamp)
        if day in activity:
            activity[day].events += 1
            activity[day].failed += 0 if log.success else 1

    week_ago = now - timedelta(days=7)

    def recent(log: AccessLog) -> bool:
        return _as_utc(log.timestamp) >= week_ago

    failed_logins = sum(1 for log in logs if log.action == "login" and not log.success and recent(log))
    active_users = len({log.user_id for log in logs if log.user_id and log.success and recent(log)})
    recent_events = sorted(logs, key=lambda log: log.timestamp, reverse=True)[:8]

    return StatsResponse(
        total_documents=len(documents),
        total_bytes=sum(d.size_bytes for d in documents),
        sensitive_documents=by_sensitivity["confidencial"] + by_sensitivity["restringido"],
        average_risk=round(sum(d.risk_score for d in documents) / len(documents), 1) if documents else 0.0,
        indexed_documents=len(indexed_ids),
        by_category=[CountItem(label=k, value=v) for k, v in by_category.most_common()],
        by_sensitivity=[CountItem(label=level, value=by_sensitivity[level]) for level in SENSITIVITY_ORDER],
        top_findings=[CountItem(label=k, value=v) for k, v in findings.most_common(6)],
        activity=list(activity.values()),
        failed_logins_7d=failed_logins,
        active_users_7d=active_users,
        total_users=db.scalar(select(func.count(User.id))) if is_admin else None,
        recent_events=[AccessLogOut.model_validate(log) for log in recent_events],
    )
