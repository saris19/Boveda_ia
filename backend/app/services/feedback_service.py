"""Retraining of the document classifier with the corrections people make."""
from __future__ import annotations

import threading

from sqlalchemy import select

from app.ai.classifier import ModelInfo, get_classifier, retrain_classifier
from app.database import SessionLocal
from app.models import ClassificationFeedback

_lock = threading.Lock()


def load_feedback() -> list[tuple[str, str]]:
    with SessionLocal() as db:
        rows = db.scalars(select(ClassificationFeedback).order_by(ClassificationFeedback.id)).all()
        return [(row.training_text, row.corrected_category) for row in rows]


def retrain_from_feedback() -> ModelInfo:
    """Seed corpus + every stored correction. Serialized so two corrections never train at once."""
    with _lock:
        return retrain_classifier(load_feedback())


def model_info() -> ModelInfo:
    return get_classifier().info
