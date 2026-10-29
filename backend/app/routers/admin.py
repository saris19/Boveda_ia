"""Security center (admin): key hierarchy and rotation, AI models and sensitivity policies."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.crypto.keyring import keyring_status, rotate_master_key
from app.database import get_db
from app.models import ClassificationFeedback, Role, User
from app.security import require_roles
from app.services.alert_service import model_status
from app.services.audit_service import log_access
from app.services.feedback_service import model_info, retrain_from_feedback
from app.services.policy_service import POLICIES

router = APIRouter(prefix="/api/admin", tags=["Centro de seguridad"])
admin_only = require_roles(Role.ADMIN)


def _classifier_payload(db: Session) -> dict:
    info = model_info()
    corrections = db.execute(
        select(ClassificationFeedback.predicted_category, ClassificationFeedback.corrected_category, func.count())
        .group_by(ClassificationFeedback.predicted_category, ClassificationFeedback.corrected_category)
    ).all()
    return {
        "algorithm": "TF-IDF palabras (1-2) + caracteres (3-5) → regresión logística",
        "trained_at": info.trained_at,
        "seed_samples": info.seed_samples,
        "feedback_samples": info.feedback_samples,
        "cv_accuracy": info.cv_accuracy,
        "categories": info.categories,
        "corrections": [{"from": a, "to": b, "count": c} for a, b, c in corrections],
    }


@router.get("/security", summary="Estado del centro de seguridad")
def security_overview(db: Session = Depends(get_db), _: User = Depends(admin_only)):
    return {
        "keyring": keyring_status(db),
        "classifier": _classifier_payload(db),
        "anomaly_model": model_status(),
        "policies": POLICIES,
    }


@router.post("/rotate-key", summary="Rotar la llave maestra")
def rotate_key(request: Request, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    result = rotate_master_key(db, admin.id)
    log_access(db, request, "key_rotation", user=admin,
               detail=f"v{result['previous_version']} → v{result['new_version']} ({result['rewrapped_keys']} llaves)")
    return result


@router.post("/classifier/retrain", summary="Reentrenar el clasificador con las correcciones")
def retrain_classifier(request: Request, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    retrain_from_feedback()
    log_access(db, request, "model_retrain", user=admin, detail="clasificador de documentos")
    return _classifier_payload(db)
