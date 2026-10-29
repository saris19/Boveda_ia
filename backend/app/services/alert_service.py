"""Suspicious-access detection: explainable rules + Isolation Forest, alerts and automatic responses.

Every audit event goes through `evaluate_event` right after it is written. Rules catch well-known
attack patterns with clear thresholds; the anomaly model catches unusual combinations the rules do
not describe. Alerts are de-duplicated: the same rule for the same user/IP within 30 minutes updates
the existing alert (and may escalate it) instead of creating a new one.
"""
from __future__ import annotations

import threading
import traceback
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import config
from app.ai.anomaly import Event, build_features, detector
from app.database import SessionLocal
from app.models import AccessLog, AlertSeverity, AlertStatus, Document, SecurityAlert, SensitivityLevel, User

DEDUP_MINUTES = 30
ML_THRESHOLD = 60.0
ML_ACTIONS = {"login", "download", "view", "share", "delete", "purge", "search", "new_version"}
SEVERITY_ORDER = [AlertSeverity.LOW, AlertSeverity.MEDIUM, AlertSeverity.HIGH, AlertSeverity.CRITICAL]

RULES = [
    {"code": "brute_force", "name": "Fuerza bruta", "severity": "alta / crítica",
     "description": "3 o más inicios de sesión fallidos para el mismo usuario en 10 minutos (crítica desde 5: la cuenta se bloquea)."},
    {"code": "credential_stuffing", "name": "Ataque desde una IP", "severity": "crítica",
     "description": "Una misma IP falla con 3 o más usuarios distintos en 10 minutos. La IP queda bloqueada para iniciar sesión 15 minutos."},
    {"code": "mass_download", "name": "Descarga masiva", "severity": "alta / crítica",
     "description": "10 o más descargas del mismo usuario en 10 minutos (crítica si incluye documentos restringidos). Sus descargas se pausan 15 minutos."},
    {"code": "access_denied", "name": "Accesos denegados repetidos", "severity": "media / alta",
     "description": "3 o más intentos a documentos sin permiso en 10 minutos (alta desde 6)."},
    {"code": "off_hours", "name": "Acceso fuera de horario", "severity": "media",
     "description": "Consulta o descarga de un documento confidencial o restringido entre las 22:00 y las 06:00."},
    {"code": "new_ip", "name": "Inicio de sesión desde IP nueva", "severity": "baja",
     "description": "Inicio de sesión exitoso desde una IP que el usuario nunca había usado (con al menos 3 ingresos previos)."},
    {"code": "enumeration", "name": "Exploración masiva", "severity": "media",
     "description": "25 o más búsquedas o consultas en 5 minutos: posible intento de recorrer la bóveda."},
    {"code": "ml_anomaly", "name": "Comportamiento anómalo (IA)", "severity": "media / alta",
     "description": "El modelo Isolation Forest considera la acción atípica frente al comportamiento normal aprendido."},
]

_train_lock = threading.Lock()


@dataclass
class Finding:
    rule: str
    severity: AlertSeverity
    title: str
    description: str
    score: float = 0.0
    response: str = ""


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _count(db: Session, *conditions) -> int:
    return db.scalar(select(func.count(AccessLog.id)).where(*conditions)) or 0


def _actor_filter(log: AccessLog):
    return AccessLog.user_id == log.user_id if log.user_id else AccessLog.username == log.username


# ------------------------------------------------------------------ rules


def _rule_findings(db: Session, log: AccessLog, user: User | None) -> list[Finding]:
    now = _utc(log.timestamp)
    last_10 = now - timedelta(minutes=10)
    findings: list[Finding] = []

    if log.action == "login" and not log.success:
        failed_user = _count(db, AccessLog.action == "login", AccessLog.success.is_(False),
                             AccessLog.username == log.username, AccessLog.timestamp >= last_10)
        if failed_user >= 3:
            critical = failed_user >= config.MAX_FAILED_LOGINS
            findings.append(Finding(
                "brute_force", AlertSeverity.CRITICAL if critical else AlertSeverity.HIGH,
                f"Posible fuerza bruta contra «{log.username}»",
                f"{failed_user} intentos fallidos de inicio de sesión en 10 minutos desde {log.ip_address or 'IP desconocida'}.",
                response="Cuenta bloqueada 15 minutos" if critical else "",
            ))
        if log.ip_address:
            distinct_users = db.scalar(
                select(func.count(func.distinct(AccessLog.username))).where(
                    AccessLog.action == "login", AccessLog.success.is_(False),
                    AccessLog.ip_address == log.ip_address, AccessLog.timestamp >= last_10,
                )
            ) or 0
            if distinct_users >= 3:
                findings.append(Finding(
                    "credential_stuffing", AlertSeverity.CRITICAL,
                    f"Ataque de credenciales desde {log.ip_address}",
                    f"La IP {log.ip_address} falló el inicio de sesión con {distinct_users} usuarios distintos en 10 minutos.",
                    response="IP bloqueada para iniciar sesión durante 15 minutos",
                ))

    if log.action == "download" and log.success and log.user_id:
        downloads = _count(db, AccessLog.action == "download", AccessLog.success.is_(True),
                           AccessLog.user_id == log.user_id, AccessLog.timestamp >= last_10)
        if downloads >= 10:
            restricted = "restringido" in (log.detail or "") or db.scalar(
                select(func.count(AccessLog.id)).where(
                    AccessLog.action == "download", AccessLog.user_id == log.user_id,
                    AccessLog.timestamp >= last_10, AccessLog.detail.like("%restringido%"),
                )
            )
            response = ""
            if user is not None:
                user.downloads_blocked_until = now + timedelta(minutes=config.DOWNLOAD_BLOCK_MINUTES)
                response = f"Descargas pausadas {config.DOWNLOAD_BLOCK_MINUTES} minutos"
            findings.append(Finding(
                "mass_download", AlertSeverity.CRITICAL if restricted else AlertSeverity.HIGH,
                f"Descarga masiva de «{log.username}»",
                f"{downloads} descargas en 10 minutos" + (", incluidos documentos restringidos." if restricted else "."),
                response=response,
            ))

    if not log.success and log.action != "login" and log.user_id:
        denied = _count(db, AccessLog.success.is_(False), AccessLog.action != "login",
                        AccessLog.user_id == log.user_id, AccessLog.timestamp >= last_10)
        if denied >= 3:
            findings.append(Finding(
                "access_denied", AlertSeverity.HIGH if denied >= 6 else AlertSeverity.MEDIUM,
                f"Accesos denegados repetidos de «{log.username}»",
                f"{denied} intentos de acceder a documentos sin permiso en 10 minutos.",
            ))

    if log.action in ("download", "view") and log.success and log.document_id:
        local = now.astimezone(ZoneInfo(config.TIMEZONE))
        off_hours = local.hour >= config.OFF_HOURS_START or local.hour < config.OFF_HOURS_END
        if off_hours:
            sensitivity = db.scalar(select(Document.sensitivity).where(Document.id == log.document_id))
            if sensitivity in (SensitivityLevel.CONFIDENTIAL, SensitivityLevel.RESTRICTED):
                findings.append(Finding(
                    "off_hours", AlertSeverity.MEDIUM,
                    f"Acceso fuera de horario de «{log.username}»",
                    f"{'Descarga' if log.action == 'download' else 'Consulta'} de un documento {sensitivity.value} "
                    f"a las {local:%H:%M}.",
                ))

    if log.action == "login" and log.success and log.user_id and log.ip_address:
        previous = db.scalars(
            select(AccessLog.ip_address).where(
                AccessLog.user_id == log.user_id, AccessLog.action == "login",
                AccessLog.success.is_(True), AccessLog.id != log.id,
            )
        ).all()
        if len(previous) >= 3 and log.ip_address not in set(previous):
            findings.append(Finding(
                "new_ip", AlertSeverity.LOW, f"Nuevo origen de inicio de sesión para «{log.username}»",
                f"Primer inicio de sesión desde {log.ip_address}.",
            ))

    if log.action in ("search", "view") and log.user_id:
        browsing = _count(db, AccessLog.action.in_(["search", "view"]), AccessLog.user_id == log.user_id,
                          AccessLog.timestamp >= now - timedelta(minutes=5))
        if browsing >= 25:
            findings.append(Finding(
                "enumeration", AlertSeverity.MEDIUM, f"Exploración masiva de «{log.username}»",
                f"{browsing} búsquedas o consultas en 5 minutos.",
            ))
    return findings


# ------------------------------------------------------------------ machine learning


def _to_event(log: AccessLog) -> Event:
    actor = log.username or f"ip:{log.ip_address}"
    return Event(_utc(log.timestamp), actor, log.action, bool(log.success), log.ip_address or "", log.document_id)


def _sensitivity_map(db: Session) -> dict[str, str]:
    return {doc_id: level.value for doc_id, level in db.execute(select(Document.id, Document.sensitivity)).all()}


def train_model(db: Session | None = None) -> dict:
    """(Re)train the anomaly model with the synthetic baseline plus the real access log."""
    own = db is None
    db = db or SessionLocal()
    try:
        with _train_lock:
            logs = db.scalars(select(AccessLog).order_by(AccessLog.id.desc()).limit(5000)).all()
            events = [_to_event(log) for log in reversed(logs)]
            state = detector.train(events, _sensitivity_map(db))
        return model_status()
    finally:
        if own:
            db.close()


def model_status() -> dict:
    state = detector.state
    if state is None:
        return {"trained": False}
    return {
        "trained": True,
        "algorithm": "Isolation Forest (200 árboles, contaminación 2 %)",
        "trained_at": state.trained_at,
        "real_events": state.real_events,
        "synthetic_events": state.synthetic_events,
        "events_since_training": state.events_since_training,
        "retrain_every": 200,
        "features": state.feature_names,
        "threshold": ML_THRESHOLD,
    }


def _ml_finding(db: Session, log: AccessLog) -> Finding | None:
    if log.action not in ML_ACTIONS or detector.state is None:
        return None
    history_rows = db.scalars(
        select(AccessLog).where(_actor_filter(log), AccessLog.id != log.id).order_by(AccessLog.id.desc()).limit(300)
    ).all()
    history = [_to_event(row) for row in reversed(history_rows)]
    sensitivity = {}
    if log.document_id:
        level = db.scalar(select(Document.sensitivity).where(Document.id == log.document_id))
        if level is not None:
            sensitivity[log.document_id] = level.value
    vector = build_features(_to_event(log), history, sensitivity)
    score = detector.score(vector)
    if score < ML_THRESHOLD:
        return None
    reasons = detector.explain(vector) or ["combinación de características poco habitual"]
    return Finding(
        "ml_anomaly", AlertSeverity.HIGH if score >= 75 else AlertSeverity.MEDIUM,
        f"Comportamiento anómalo de «{log.username or log.ip_address}»",
        f"Puntaje de anomalía {score:.0f}/100 en «{log.action}»: " + "; ".join(reasons) + ".",
        score=round(score, 1),
    )


# ------------------------------------------------------------------ alerts


def _store(db: Session, log: AccessLog, finding: Finding) -> SecurityAlert:
    since = _utc(log.timestamp) - timedelta(minutes=DEDUP_MINUTES)
    subject = SecurityAlert.user_id == log.user_id if log.user_id else SecurityAlert.ip_address == log.ip_address
    if finding.rule == "credential_stuffing":
        subject = SecurityAlert.ip_address == log.ip_address
    existing = db.scalar(
        select(SecurityAlert).where(
            SecurityAlert.rule == finding.rule, subject,
            SecurityAlert.status.in_([AlertStatus.OPEN, AlertStatus.IN_REVIEW]),
            SecurityAlert.updated_at >= since,
        )
    )
    now = datetime.now(timezone.utc)
    if existing:
        existing.event_count += 1
        existing.updated_at = now
        existing.description = finding.description
        existing.score = max(existing.score, finding.score)
        if SEVERITY_ORDER.index(finding.severity) > SEVERITY_ORDER.index(existing.severity):
            existing.severity = finding.severity
        if finding.response:
            existing.response = finding.response
        return existing
    alert = SecurityAlert(
        rule=finding.rule, severity=finding.severity, title=finding.title[:120],
        description=finding.description[:500], user_id=log.user_id, username=log.username,
        ip_address=log.ip_address, document_id=log.document_id, score=finding.score,
        response=finding.response, created_at=now, updated_at=now,
    )
    db.add(alert)
    return alert


def evaluate_event(db: Session, log: AccessLog) -> list[SecurityAlert]:
    """Run rules + anomaly model for a freshly written audit event. Never raises."""
    try:
        user = db.get(User, log.user_id) if log.user_id else None
        findings = _rule_findings(db, log, user)
        ml = _ml_finding(db, log)
        if ml:
            findings.append(ml)
        alerts = [_store(db, log, finding) for finding in findings]
        db.commit()
        _maybe_retrain()
        return alerts
    except Exception:  # detection must never break the user's request
        db.rollback()
        traceback.print_exc()
        return []


def _maybe_retrain() -> None:
    state = detector.state
    if state is None:
        return
    state.events_since_training += 1
    if state.events_since_training >= 200 and not _train_lock.locked():
        state.events_since_training = 0
        threading.Thread(target=train_model, daemon=True).start()


def ip_login_blocked(db: Session, ip_address: str) -> bool:
    """Automatic response to credential stuffing: an IP with an open alert can't log in for 15 minutes."""
    if not ip_address:
        return False
    since = datetime.now(timezone.utc) - timedelta(minutes=15)
    return bool(
        db.scalar(
            select(func.count(SecurityAlert.id)).where(
                SecurityAlert.rule == "credential_stuffing", SecurityAlert.ip_address == ip_address,
                SecurityAlert.status.in_([AlertStatus.OPEN, AlertStatus.IN_REVIEW]),
                SecurityAlert.updated_at >= since,
            )
        )
    )
