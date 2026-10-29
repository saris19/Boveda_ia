"""Suspicious-access alerts (admin only)."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AlertSeverity, AlertStatus, Role, SecurityAlert, User
from app.schemas import AlertOut, AlertUpdate
from app.security import require_roles
from app.services.alert_service import RULES, model_status, train_model
from app.services.audit_service import log_access

router = APIRouter(prefix="/api/alerts", tags=["Accesos sospechosos"])
admin_only = require_roles(Role.ADMIN)
VALID_STATUS = {s.value for s in AlertStatus}


@router.get("", response_model=list[AlertOut], summary="Listar alertas")
def list_alerts(
    status: str | None = None,
    severity: str | None = None,
    limit: int = Query(200, le=1000),
    db: Session = Depends(get_db),
    _: User = Depends(admin_only),
):
    query = select(SecurityAlert).order_by(SecurityAlert.updated_at.desc()).limit(limit)
    if status == "activas":
        query = query.where(SecurityAlert.status.in_([AlertStatus.OPEN, AlertStatus.IN_REVIEW]))
    elif status in VALID_STATUS:
        query = query.where(SecurityAlert.status == AlertStatus(status))
    if severity in {s.value for s in AlertSeverity}:
        query = query.where(SecurityAlert.severity == AlertSeverity(severity))
    return [AlertOut.model_validate(a).model_copy(update={"severity": a.severity.value, "status": a.status.value})
            for a in db.scalars(query).all()]


@router.get("/summary", summary="Resumen de seguridad")
def summary(tz_offset: int = Query(0, ge=-840, le=840), db: Session = Depends(get_db), _: User = Depends(admin_only)):
    alerts = db.scalars(select(SecurityAlert)).all()
    active = [a for a in alerts if a.status in (AlertStatus.OPEN, AlertStatus.IN_REVIEW)]
    zone = timezone(timedelta(minutes=tz_offset))
    today = datetime.now(timezone.utc).astimezone(zone).date()
    days = [(today - timedelta(days=13 - i)).isoformat() for i in range(14)]
    per_day = Counter(
        (a.created_at if a.created_at.tzinfo else a.created_at.replace(tzinfo=timezone.utc)).astimezone(zone).date().isoformat()
        for a in alerts
    )
    return {
        "active_total": len(active),
        "active_by_severity": {s.value: sum(1 for a in active if a.severity == s) for s in AlertSeverity},
        "total": len(alerts),
        "by_rule": dict(Counter(a.rule for a in alerts).most_common()),
        "per_day": [{"date": d, "alerts": per_day.get(d, 0)} for d in days],
        "top_subjects": [
            {"subject": subject, "alerts": count}
            for subject, count in Counter(a.username or a.ip_address for a in active).most_common(5)
        ],
        "rules": RULES,
        "model": model_status(),
    }


@router.patch("/{alert_id}", response_model=AlertOut, summary="Cambiar estado de una alerta")
def update_alert(
    alert_id: int, payload: AlertUpdate, request: Request, db: Session = Depends(get_db), admin: User = Depends(admin_only)
):
    alert = db.get(SecurityAlert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alerta no encontrada.")
    if payload.status is not None:
        if payload.status not in VALID_STATUS:
            raise HTTPException(status_code=400, detail="Estado no válido.")
        alert.status = AlertStatus(payload.status)
        if alert.status in (AlertStatus.RESOLVED, AlertStatus.FALSE_POSITIVE):
            alert.resolved_by = admin.id
            alert.resolved_at = datetime.now(timezone.utc)
        else:
            alert.resolved_by = None
            alert.resolved_at = None
    if payload.notes is not None:
        alert.notes = payload.notes
    alert.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(alert)
    log_access(db, request, "alert_update", user=admin, detail=f"alerta {alert.id} → {alert.status.value}")
    return AlertOut.model_validate(alert).model_copy(update={"severity": alert.severity.value, "status": alert.status.value})


@router.post("/model/retrain", summary="Reentrenar el modelo de anomalías")
def retrain(db: Session = Depends(get_db), _: User = Depends(admin_only)):
    return train_model(db)
