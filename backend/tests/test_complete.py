"""Tests of the final scope (100 %): versions, recycle bin, sensitivity policies, classification
feedback, master-key rotation and suspicious-access detection."""
import numpy as np
from fastapi.testclient import TestClient

from app import config
from app.ai.anomaly import FEATURES, detector, synthetic_baseline
from app.database import SessionLocal
from app.main import app
from app.models import ClassificationFeedback, Document, MasterKey
from tests.conftest import login

HR_TEXT = "Certificado laboral de la empresa. Contrato a término indefinido, cargo de analista y salario.".encode()
HEALTH_TEXT = "Historia clínica: diagnóstico de hipertensión, medicamento y control médico.".encode()
PLAIN_TEXT = "Acta de reunión del comité directivo con compromisos y cronograma de actividades.".encode()


def _user(client, admin_headers, username, role="editor"):
    client.post("/api/users", headers=admin_headers, json={"username": username, "password": "Clave123*", "role": role})
    return login(client, username, "Clave123*")


def _upload(client, headers, name, content):
    response = client.post("/api/documents", headers=headers, files={"file": (name, content)})
    assert response.status_code == 201, response.text
    return response.json()


def _alerts(client, admin_headers, rule):
    return [a for a in client.get("/api/alerts", headers=admin_headers).json() if a["rule"] == rule]


# ------------------------------------------------------------------ versions and recycle bin


def test_versions_and_restore(client, admin_headers):
    editor = _user(client, admin_headers, "ver_editor")
    doc = _upload(client, editor, "politica.txt", b"Version uno del procedimiento de archivo y correspondencia.")

    v2 = client.post(f"/api/documents/{doc['id']}/versions", headers=editor,
                     files={"file": ("politica.txt", b"Version dos: procedimiento de radicacion con firewall nuevo.")})
    assert v2.status_code == 201 and v2.json()["version_number"] == 2

    versions = client.get(f"/api/documents/{doc['id']}/versions", headers=editor).json()
    assert [v["version_number"] for v in versions] == [2, 1] and versions[0]["is_current"]

    assert client.get(f"/api/documents/{doc['id']}/download", headers=editor).content.startswith(b"Version dos")
    assert client.get(f"/api/documents/{doc['id']}/versions/1/download", headers=editor).content.startswith(b"Version uno")

    # The blind index follows the current content
    names = [r["document"]["original_name"] for r in client.get("/api/search", params={"q": "firewall"}, headers=editor).json()["results"]]
    assert "politica.txt" in names

    restored = client.post(f"/api/documents/{doc['id']}/versions/1/restore", headers=editor).json()
    assert restored["version_number"] == 3
    assert client.get(f"/api/documents/{doc['id']}/download", headers=editor).content.startswith(b"Version uno")
    assert len(client.get(f"/api/documents/{doc['id']}/versions", headers=editor).json()) == 3


def test_trash_restore(client, admin_headers):
    editor = _user(client, admin_headers, "trash_editor")
    doc = _upload(client, editor, "acta.txt", PLAIN_TEXT)
    client.delete(f"/api/documents/{doc['id']}", headers=editor)
    assert doc["id"] not in [d["id"] for d in client.get("/api/documents", headers=editor).json()]
    item = next(d for d in client.get("/api/trash", headers=editor).json() if d["id"] == doc["id"])
    assert item["deleted_by_username"] == "trash_editor" and item["purge_at"]
    assert client.post(f"/api/trash/{doc['id']}/restore", headers=editor).status_code == 204
    assert doc["id"] in [d["id"] for d in client.get("/api/documents", headers=editor).json()]


# ------------------------------------------------------------------ sensitivity policies


def test_confidential_policy(client, admin_headers):
    owner = _user(client, admin_headers, "pol_owner")
    other_editor = _user(client, admin_headers, "pol_editor")
    viewer = _user(client, admin_headers, "pol_viewer", "viewer")
    doc = _upload(client, owner, "historia.txt", HEALTH_TEXT)
    assert doc["sensitivity"] == "confidencial"

    denied = client.post(f"/api/documents/{doc['id']}/share", headers=owner, json={"role": "viewer"})
    assert denied.status_code == 400
    assert client.post(f"/api/documents/{doc['id']}/share", headers=owner, json={"role": "editor"}).status_code == 201
    assert client.get(f"/api/documents/{doc['id']}/download", headers=other_editor).status_code == 200
    assert client.get(f"/api/documents/{doc['id']}/download", headers=viewer).status_code == 403

    # Raising the level to "restringido" removes the role access immediately
    client.patch(f"/api/documents/{doc['id']}/classification", headers=owner, json={"sensitivity": "restringido"})
    assert client.get(f"/api/documents/{doc['id']}/download", headers=other_editor).status_code == 403
    assert doc["id"] not in [d["id"] for d in client.get("/api/documents", headers=other_editor).json()]


# ------------------------------------------------------------------ classification feedback


def test_classification_feedback_retrains(client, admin_headers):
    editor = _user(client, admin_headers, "fb_editor")
    text = "Constancia emitida por Gómez Rivera para la empresa: contrato de prestación y honorarios.".encode()
    doc = _upload(client, editor, "constancia.txt", text)
    before = client.get("/api/admin/security", headers=admin_headers).json()["classifier"]["feedback_samples"]

    corrected = client.patch(f"/api/documents/{doc['id']}/classification", headers=editor,
                             json={"category": "Legal" if doc["category"] != "Legal" else "Financiero"})
    assert corrected.status_code == 200 and corrected.json()["manual_classification"] is True

    with SessionLocal() as db:
        feedback = db.query(ClassificationFeedback).filter_by(document_id=doc["id"]).one()
        assert "gomez" not in feedback.training_text and "rivera" not in feedback.training_text
        assert "contrato" in feedback.training_text

    after = client.post("/api/admin/classifier/retrain", headers=admin_headers).json()
    assert after["feedback_samples"] == before + 1 and 0 < after["cv_accuracy"] <= 1
    assert client.patch(f"/api/documents/{doc['id']}/classification", headers=editor,
                        json={"category": "Inventada"}).status_code == 400

    # Leave the shared model as it was for the other tests
    with SessionLocal() as db:
        db.query(ClassificationFeedback).delete()
        db.commit()
    client.post("/api/admin/classifier/retrain", headers=admin_headers)


# ------------------------------------------------------------------ key rotation


def test_master_key_rotation(client, admin_headers):
    editor = _user(client, admin_headers, "key_editor")
    doc = _upload(client, editor, "rot.txt", PLAIN_TEXT)
    client.post(f"/api/documents/{doc['id']}/versions", headers=editor, files={"file": ("rot.txt", HR_TEXT)})

    first = client.post("/api/admin/rotate-key", headers=admin_headers).json()
    second = client.post("/api/admin/rotate-key", headers=admin_headers).json()
    assert second["new_version"] == first["new_version"] + 1 and second["rewrapped_keys"] >= 2

    # Every document (and old version) is still readable with the new key
    assert client.get(f"/api/documents/{doc['id']}/download", headers=editor).content == HR_TEXT
    assert client.get(f"/api/documents/{doc['id']}/versions/1/download", headers=editor).content == PLAIN_TEXT
    with SessionLocal() as db:
        assert {d.key_version for d in db.query(Document).all()} == {second["new_version"]}
        assert [k.version for k in db.query(MasterKey).filter_by(active=True)] == [second["new_version"]]
    status = client.get("/api/admin/security", headers=admin_headers).json()["keyring"]
    assert status["active_version"] == second["new_version"]
    # Uploads after rotation use the new key too
    new_doc = _upload(client, editor, "nuevo.txt", PLAIN_TEXT)
    assert new_doc["key_version"] == second["new_version"]
    assert client.get("/api/admin/security", headers=editor).status_code == 403


# ------------------------------------------------------------------ suspicious access detection


def test_bruteforce_and_credential_stuffing_alerts(client, admin_headers):
    _user(client, admin_headers, "bf_target", "viewer")
    attacker = TestClient(app, client=("203.0.113.50", 40000))
    for _ in range(3):
        attacker.post("/api/auth/login", data={"username": "bf_target", "password": "x"})
    alert = _alerts(client, admin_headers, "brute_force")
    assert any(a["username"] == "bf_target" and a["severity"] in ("alta", "critica") for a in alert)

    for name in ("nadie1", "nadie2", "nadie3"):
        attacker.post("/api/auth/login", data={"username": name, "password": "x"})
    stuffing = _alerts(client, admin_headers, "credential_stuffing")
    assert stuffing and stuffing[0]["ip_address"] == "203.0.113.50" and stuffing[0]["severity"] == "critica"
    # Automatic response: the IP can't log in even with the right password
    blocked = attacker.post("/api/auth/login", data={"username": "admin", "password": "Admin123*"})
    assert blocked.status_code == 429


def test_mass_download_blocks_and_unblock(client, admin_headers):
    editor = _user(client, admin_headers, "md_editor")
    doc = _upload(client, editor, "acta_md.txt", PLAIN_TEXT)
    for _ in range(10):
        assert client.get(f"/api/documents/{doc['id']}/download", headers=editor).status_code == 200
    alert = _alerts(client, admin_headers, "mass_download")
    assert alert and alert[0]["username"] == "md_editor" and "pausadas" in alert[0]["response"]
    assert client.get(f"/api/documents/{doc['id']}/download", headers=editor).status_code == 429

    user_id = next(u["id"] for u in client.get("/api/users", headers=admin_headers).json() if u["username"] == "md_editor")
    client.post(f"/api/users/{user_id}/unblock", headers=admin_headers)
    assert client.get(f"/api/documents/{doc['id']}/download", headers=editor).status_code == 200

    # Alert workflow
    updated = client.patch(f"/api/alerts/{alert[0]['id']}", headers=admin_headers,
                           json={"status": "resuelta", "notes": "Prueba de carga autorizada"}).json()
    assert updated["status"] == "resuelta" and updated["resolved_at"]


def test_access_denied_and_off_hours(client, admin_headers, monkeypatch):
    owner = _user(client, admin_headers, "oh_owner")
    snoop = _user(client, admin_headers, "oh_snoop", "viewer")
    doc = _upload(client, owner, "historia_oh.txt", HEALTH_TEXT)
    for _ in range(3):
        client.get(f"/api/documents/{doc['id']}/download", headers=snoop)
    assert any(a["username"] == "oh_snoop" for a in _alerts(client, admin_headers, "access_denied"))

    # Force "now" to be off-hours by moving the window to cover the whole day
    monkeypatch.setattr(config, "OFF_HOURS_START", 0)
    client.get(f"/api/documents/{doc['id']}/download", headers=owner)
    assert any(a["username"] == "oh_owner" for a in _alerts(client, admin_headers, "off_hours"))


def test_anomaly_model_scores_and_explains():
    detector_state = detector.state
    assert detector_state is not None and detector_state.synthetic_events > 0
    normal = synthetic_baseline(50, seed=7)
    assert np.mean([detector.score(row) for row in normal]) < 50

    # 3 a.m. on a Sunday, 40 downloads in an hour, failures, new IP, restricted document
    attack = np.array([
        np.sin(2 * np.pi * 3 / 24), np.cos(2 * np.pi * 3 / 24), 1.0, 1.0, 0.6,
        np.log1p(30), np.log1p(40), np.log1p(6), np.log1p(25), 1.0, 1.0, 0.7,
    ])
    assert len(attack) == len(FEATURES)
    assert detector.score(attack) >= 60
    reasons = " ".join(detector.explain(attack))
    assert "descargas" in reasons or "hora inusual" in reasons


def test_alert_summary_and_permissions(client, admin_headers):
    summary = client.get("/api/alerts/summary", headers=admin_headers).json()
    assert summary["total"] >= 3 and len(summary["per_day"]) == 14
    assert {r["code"] for r in summary["rules"]} >= {"brute_force", "mass_download", "ml_anomaly"}
    assert summary["model"]["trained"] is True
    retrained = client.post("/api/alerts/model/retrain", headers=admin_headers).json()
    assert retrained["real_events"] > 0
    viewer = _user(client, admin_headers, "sum_viewer", "viewer")
    assert client.get("/api/alerts", headers=viewer).status_code == 403
