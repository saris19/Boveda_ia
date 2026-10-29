"""Tests for the 50% scope: blind index, smart search, dashboard stats and schema migration."""
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from app.ai.search_index import build_blind_index, extract_stems
from app.database import SessionLocal
from app.migrations import run_migrations
from app.models import Document
from tests.conftest import login

EXAMPLES = Path(__file__).resolve().parents[2] / "ejemplos"


def test_blind_index_hides_words():
    index = build_blind_index("Factura del proveedor con pago pendiente")
    assert index and all(len(token) == 16 for token in index)
    assert not any("factur" in token for token in index)
    # Same root for singular/plural so 'facturas' finds 'factura'
    assert extract_stems("facturas")[0] == extract_stems("factura")[0]


def _upload_examples(client, headers):
    ids = {}
    for path in sorted(EXAMPLES.iterdir()):
        response = client.post("/api/documents", headers=headers, files={"file": (path.name, path.read_bytes())})
        assert response.status_code == 201, response.text
        ids[path.name] = response.json()["id"]
    return ids


def test_search_and_stats(client, admin_headers):
    client.post("/api/users", headers=admin_headers, json={"username": "editor_s", "password": "Clave123*", "role": "editor"})
    client.post("/api/users", headers=admin_headers, json={"username": "lector_s", "password": "Clave123*", "role": "viewer"})
    editor = login(client, "editor_s", "Clave123*")
    viewer = login(client, "lector_s", "Clave123*")
    ids = _upload_examples(client, editor)

    # Plaintext words are not stored anywhere in the document row
    with SessionLocal() as db:
        row = db.get(Document, ids["historia_clinica.txt"])
        assert "losartan" not in str(row.search_index).lower()

    # Content search inside the encrypted file (word only present in the body)
    data = client.get("/api/search", params={"q": "losartán"}, headers=editor).json()
    assert data["results"][0]["document"]["original_name"] == "historia_clinica.txt"
    assert any("contenido cifrado" in r for r in data["results"][0]["reasons"])

    # Plural / singular and typo tolerance on metadata
    data = client.get("/api/search", params={"q": "facturas"}, headers=editor).json()
    assert data["results"][0]["document"]["original_name"] == "factura_proveedor.txt"
    data = client.get("/api/search", params={"q": "certificdo"}, headers=editor).json()
    assert data["results"] and data["results"][0]["document"]["original_name"] == "certificado_laboral.txt"

    # AI intent: the model links the query to a category
    data = client.get("/api/search", params={"q": "paciente"}, headers=editor).json()
    assert data["intent"]["category"] == "Salud"

    # Structured filters
    data = client.get("/api/search", params={"sensitivity": "restringido"}, headers=editor).json()
    assert data["total"] == 3 and all(r["document"]["sensitivity"] == "restringido" for r in data["results"])

    # Viewer only sees what is shared with them
    assert client.get("/api/search", params={"q": "factura"}, headers=viewer).json()["total"] == 0
    client.post(f"/api/documents/{ids['factura_proveedor.txt']}/share", headers=editor, json={"username": "lector_s"})
    assert client.get("/api/search", params={"q": "factura"}, headers=viewer).json()["total"] == 1

    # The query text is never written to the audit log
    audit = client.get("/api/audit", headers=admin_headers).json()
    assert not any("losart" in entry["detail"] for entry in audit)

    # Dashboard
    stats = client.get("/api/stats", headers=editor).json()
    assert stats["total_documents"] == 6 and stats["indexed_documents"] == 6
    assert stats["sensitive_documents"] == 4
    assert {c["label"] for c in stats["by_category"]} >= {"Salud", "Financiero"}
    assert sum(day["uploads"] for day in stats["activity"]) == 6
    # Local-time bucketing (Colombia, UTC-5) still counts every upload in the last 14 local days
    local = client.get("/api/stats", params={"tz_offset": -300}, headers=editor).json()
    assert sum(day["uploads"] for day in local["activity"]) == 6 and len(local["activity"]) == 14
    assert stats["total_users"] is None  # only admins get user counts
    assert client.get("/api/stats", headers=viewer).json()["total_documents"] == 1
    assert client.get("/api/stats", headers=admin_headers).json()["total_users"] >= 3


def test_migration_adds_missing_column(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE documents (id VARCHAR(36) PRIMARY KEY)"))
    applied = run_migrations(engine)
    assert "documents.search_index" in applied and "documents.deleted_at" in applied
    columns = {c["name"] for c in inspect(engine).get_columns("documents")}
    assert {"search_index", "key_version", "version_number", "deleted_at", "manual_classification"} <= columns
    assert run_migrations(engine) == []  # idempotent
