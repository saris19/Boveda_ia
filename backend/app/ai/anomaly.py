"""Suspicious-access detection with an Isolation Forest over the access log.

Each event of the audit trail becomes a vector of behavioural features (time of day, volume of
activity, failures, new IP, sensitivity of the document...). The Isolation Forest learns what
"normal" looks like and isolates events that are rare in several dimensions at once.

Cold start: a brand-new vault has no history, so the model starts from a synthetic baseline of normal
office behaviour (documented and reproducible, seed 42) and is retrained with the real log as it grows.
"""
from __future__ import annotations

import math
import threading
from bisect import bisect_left
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np
from sklearn.ensemble import IsolationForest

from app import config

FEATURES = [
    "hour_sin",
    "hour_cos",
    "is_weekend",
    "is_failure",
    "action_risk",
    "events_10m",
    "downloads_60m",
    "failures_60m",
    "distinct_docs_60m",
    "new_ip",
    "sensitivity",
    "hour_deviation",
]
ACTION_RISK = {
    "login": 0.2, "search": 0.1, "view": 0.2, "download": 0.6, "share": 0.5, "revoke": 0.3,
    "delete": 0.7, "purge": 0.9, "classify": 0.3, "upload": 0.3, "new_version": 0.3,
}
SENSITIVITY_ORDINAL = {"publico": 0, "interno": 1, "confidencial": 2, "restringido": 3}
SYNTHETIC_EVENTS = 1500
MAX_TRAINING_EVENTS = 5000
RETRAIN_EVERY = 200
CONTAMINATION = 0.02


@dataclass
class Event:
    """Minimal view of an AccessLog row (keeps the model independent from the ORM)."""

    timestamp: datetime
    actor: str              # username, or "ip:<address>" for anonymous attempts
    action: str
    success: bool
    ip_address: str
    document_id: str | None


@dataclass
class ModelState:
    model: IsolationForest
    mean: np.ndarray
    std: np.ndarray
    trained_at: datetime
    real_events: int
    synthetic_events: int
    anomalies_in_training: int
    events_since_training: int = 0
    feature_names: list[str] = field(default_factory=lambda: list(FEATURES))


def _local(ts: datetime) -> datetime:
    ts = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(ZoneInfo(config.TIMEZONE))


def _circular_hour_distance(a: float, b: float) -> float:
    d = abs(a - b) % 24
    return min(d, 24 - d)


def build_features(event: Event, history: list[Event], sensitivity: dict[str, str]) -> np.ndarray:
    """Features of `event` given the same actor's previous events (oldest first)."""
    local = _local(event.timestamp)
    hour = local.hour + local.minute / 60
    stamps = [h.timestamp for h in history]

    def window(minutes: int) -> list[Event]:
        start = bisect_left(stamps, event.timestamp - timedelta(minutes=minutes))
        return history[start:]

    last_10 = window(10)
    last_60 = window(60)
    downloads = sum(1 for h in last_60 if h.action == "download" and h.success) + (event.action == "download")
    failures = sum(1 for h in last_60 if not h.success) + (not event.success)
    documents = {h.document_id for h in last_60 if h.document_id} | ({event.document_id} if event.document_id else set())
    known_ips = {h.ip_address for h in history if h.success}
    new_ip = 1.0 if history and event.ip_address and event.ip_address not in known_ips else 0.0
    hours = [_local(h.timestamp).hour + _local(h.timestamp).minute / 60 for h in history[-200:]]
    if len(hours) >= 5:
        typical = float(np.median(hours))
        deviation = _circular_hour_distance(hour, typical) / 12
    else:
        deviation = 0.0
    return np.array(
        [
            math.sin(2 * math.pi * hour / 24),
            math.cos(2 * math.pi * hour / 24),
            1.0 if local.weekday() >= 5 else 0.0,
            0.0 if event.success else 1.0,
            ACTION_RISK.get(event.action, 0.1),
            math.log1p(len(last_10) + 1),
            math.log1p(downloads),
            math.log1p(failures),
            math.log1p(len(documents)),
            new_ip,
            SENSITIVITY_ORDINAL.get(sensitivity.get(event.document_id or "", ""), 0) / 3,
            deviation,
        ]
    )


def features_for_log(events: list[Event], sensitivity: dict[str, str]) -> np.ndarray:
    """Feature matrix for a chronological list of events (each one sees only its actor's past)."""
    by_actor: dict[str, list[Event]] = defaultdict(list)
    rows = []
    for event in sorted(events, key=lambda e: e.timestamp):
        history = by_actor[event.actor]
        rows.append(build_features(event, history, sensitivity))
        history.append(event)
    return np.array(rows) if rows else np.empty((0, len(FEATURES)))


def synthetic_baseline(n: int = SYNTHETIC_EVENTS, seed: int = 42) -> np.ndarray:
    """Normal office behaviour: weekday working hours, few downloads, rare failures, known IPs."""
    rng = np.random.default_rng(seed)
    hours = np.clip(rng.normal(11, 2.6, n), 6.5, 20)
    actions = rng.choice(list(ACTION_RISK), size=n, p=[0.15, 0.2, 0.27, 0.2, 0.03, 0.01, 0.02, 0.0, 0.02, 0.07, 0.03])
    rows = []
    for i in range(n):
        failure = rng.random() < 0.03
        rows.append(
            [
                math.sin(2 * math.pi * hours[i] / 24),
                math.cos(2 * math.pi * hours[i] / 24),
                1.0 if rng.random() < 0.06 else 0.0,
                1.0 if failure else 0.0,
                ACTION_RISK[actions[i]],
                math.log1p(rng.integers(1, 7)),
                math.log1p(rng.integers(0, 4) + (actions[i] == "download")),
                math.log1p(int(failure) + (rng.random() < 0.05)),
                math.log1p(rng.integers(0, 6)),
                1.0 if rng.random() < 0.02 else 0.0,
                rng.choice([0, 1, 2, 3], p=[0.35, 0.3, 0.2, 0.15]) / 3,
                abs(rng.normal(0, 1.4)) / 12,
            ]
        )
    return np.array(rows)


class AnomalyDetector:
    def __init__(self) -> None:
        self.state: ModelState | None = None
        self._lock = threading.Lock()

    def train(self, events: list[Event], sensitivity: dict[str, str]) -> ModelState:
        real = features_for_log(events[-MAX_TRAINING_EVENTS:], sensitivity)
        synthetic = synthetic_baseline()
        data = np.vstack([synthetic, real]) if len(real) else synthetic
        model = IsolationForest(n_estimators=200, contamination=CONTAMINATION, random_state=42).fit(data)
        state = ModelState(
            model=model,
            mean=data.mean(axis=0),
            std=data.std(axis=0) + 1e-6,
            trained_at=datetime.now(timezone.utc),
            real_events=len(real),
            synthetic_events=len(synthetic),
            anomalies_in_training=int((model.predict(data) == -1).sum()),
        )
        with self._lock:
            self.state = state
        return state

    def score(self, vector: np.ndarray) -> float:
        """Anomaly score 0-100 (≥ 60 means the forest considers the event an outlier)."""
        if self.state is None:
            return 0.0
        decision = float(self.state.model.decision_function(vector.reshape(1, -1))[0])
        return float(np.clip(50 - decision * 250, 0, 100))

    def explain(self, vector: np.ndarray, top: int = 3) -> list[str]:
        """Human-readable reasons: the features that deviate the most from the learned normal."""
        if self.state is None:
            return []
        z = (vector - self.state.mean) / self.state.std
        reasons = []
        for index in np.argsort(-np.abs(z)):
            if abs(z[index]) < 1.8 or len(reasons) >= top:
                continue
            text = _describe(FEATURES[index], vector, z[index])
            if text:
                reasons.append(text)
        return reasons


def _describe(name: str, v: np.ndarray, z: float) -> str | None:
    values = dict(zip(FEATURES, v))
    if name in ("hour_sin", "hour_cos", "hour_deviation") and z != 0:
        hour = (math.degrees(math.atan2(values["hour_sin"], values["hour_cos"])) / 15) % 24
        return f"hora inusual ({int(hour):02d}:{int((hour % 1) * 60):02d})"
    if name == "downloads_60m" and z > 0:
        return f"{round(math.expm1(values[name]))} descargas en la última hora"
    if name == "events_10m" and z > 0:
        return f"{round(math.expm1(values[name])) - 1} acciones en 10 minutos"
    if name == "failures_60m" and z > 0:
        return f"{round(math.expm1(values[name]))} intentos fallidos en la última hora"
    if name == "distinct_docs_60m" and z > 0:
        return f"{round(math.expm1(values[name]))} documentos distintos en una hora"
    if name == "new_ip" and z > 0:
        return "dirección IP nunca usada por este usuario"
    if name == "is_weekend" and z > 0:
        return "actividad en fin de semana"
    if name == "is_failure" and z > 0:
        return "la acción fue rechazada"
    if name == "sensitivity" and z > 0:
        return "documento de alta sensibilidad"
    if name == "action_risk" and z > 0:
        return "acción de alto impacto"
    return None


detector = AnomalyDetector()
