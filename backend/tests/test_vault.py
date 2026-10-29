"""End-to-end tests of the base scope: auth, roles, encryption, permissions, sensitivity policy, audit and AI."""
from app import config
from app.ai.sensitive_detector import detect_sensitive_data, luhn_is_valid, nit_is_valid
from app.crypto.vault_crypto import IntegrityError, decrypt_document, encrypt_document
from app.database import SessionLocal
from app.services.storage_service import BlobNotFoundError, load_blob
from tests.conftest import login


def read_stored_ciphertext(document_id: str) -> bytes | None:
    """Read whatever the active storage backend persisted (disk file or DB row)."""
    with SessionLocal() as db:
        storage_path = f"db://{document_id}" if config.STORAGE_BACKEND == "database" else f"{document_id}.enc"
        try:
            return load_blob(db, storage_path)
        except BlobNotFoundError:
            return None

SENSITIVE_TEXT = (
    "Certificado laboral. La señora Ana Pérez, identificada con cédula de ciudadanía 1.085.123.456, "
    "labora con contrato a término indefinido en el cargo de analista. Pago de nómina a la cuenta de ahorros 12345678901. "
    "Tarjeta corporativa 4111 1111 1111 1111. Correo ana.perez@empresa.com"
).encode("utf-8")


# ---------- Crypto ----------

def test_encrypt_decrypt_roundtrip():
    payload = encrypt_document(b"hola mundo", "doc-1")
    assert b"hola mundo" not in payload.ciphertext
    assert decrypt_document(payload.ciphertext, payload.data_nonce, payload.wrapped_key,
                            payload.key_nonce, "doc-1", payload.sha256) == b"hola mundo"


def test_tampering_is_detected():
    payload = encrypt_document(b"contenido secreto", "doc-2")
    tampered = bytes([payload.ciphertext[0] ^ 1]) + payload.ciphertext[1:]
    try:
        decrypt_document(tampered, payload.data_nonce, payload.wrapped_key, payload.key_nonce, "doc-2", payload.sha256)
        assert False, "should have failed"
    except IntegrityError:
        pass


def test_ciphertext_cannot_be_swapped_between_documents():
    payload = encrypt_document(b"abc", "doc-A")
    try:
        decrypt_document(payload.ciphertext, payload.data_nonce, payload.wrapped_key, payload.key_nonce, "doc-B", payload.sha256)
        assert False
    except IntegrityError:
        pass


# ---------- AI ----------

def test_validators():
    assert luhn_is_valid("4111111111111111")
    assert not luhn_is_valid("4111111111111112")
    assert nit_is_valid("900.123.456-8")
    assert not nit_is_valid("900.123.456-1")


def test_sensitive_detection_masks_values():
    result = detect_sensitive_data(SENSITIVE_TEXT.decode())
    assert {"credit_card", "national_id", "bank_account", "email"} <= set(result.findings)
    assert result.sensitivity.value == "restringido"
    stored = str(result.findings)
    assert "4111 1111 1111 1111" not in stored and "12345678901" not in stored


def test_clean_text_is_public():
    assert detect_sensitive_data("Acta de reunión del comité con compromisos.").sensitivity.value == "publico"


# ---------- API flow ----------

def test_full_flow(client, admin_headers):
    # Admin creates an editor and a viewer
    for username, role in (("editor1", "editor"), ("lector1", "viewer"), ("lector2", "viewer")):
        response = client.post("/api/users", headers=admin_headers,
                               json={"username": username, "password": "Clave123*", "role": role})
        assert response.status_code == 201, response.text

    weak = client.post("/api/users", headers=admin_headers, json={"username": "debil", "password": "123", "role": "viewer"})
    assert weak.status_code == 400

    editor = login(client, "editor1", "Clave123*")
    viewer = login(client, "lector1", "Clave123*")
    viewer2 = login(client, "lector2", "Clave123*")

    # Viewer cannot upload or manage users
    assert client.post("/api/documents", headers=viewer, files={"file": ("a.txt", b"hola")}).status_code == 403
    assert client.get("/api/audit", headers=viewer).status_code == 403

    # Disallowed extension
    assert client.post("/api/documents", headers=editor, files={"file": ("x.exe", b"MZ")}).status_code == 400

    # Editor uploads a sensitive HR document
    response = client.post("/api/documents", headers=editor,
                           files={"file": ("certificado.txt", SENSITIVE_TEXT, "text/plain")})
    assert response.status_code == 201, response.text
    document = response.json()
    assert document["category"] == "Recursos Humanos"
    assert document["sensitivity"] == "restringido"

    # The file on disk is encrypted
    stored_bytes = read_stored_ciphertext(document["id"])
    assert stored_bytes is not None
    assert b"Ana P" not in stored_bytes and b"4111" not in stored_bytes

    # Viewer has no access until it is shared
    assert client.get(f"/api/documents/{document['id']}/download", headers=viewer).status_code == 403
    assert client.get("/api/documents", headers=viewer).json() == []

    # Share with lector1 only
    share = client.post(f"/api/documents/{document['id']}/share", headers=editor, json={"username": "lector1"})
    assert share.status_code == 201, share.text
    download = client.get(f"/api/documents/{document['id']}/download", headers=viewer)
    assert download.status_code == 200 and download.content == SENSITIVE_TEXT
    assert client.get(f"/api/documents/{document['id']}/download", headers=viewer2).status_code == 403

    # Viewer cannot share or delete
    assert client.post(f"/api/documents/{document['id']}/share", headers=viewer, json={"username": "lector2"}).status_code == 403
    assert client.delete(f"/api/documents/{document['id']}", headers=viewer).status_code == 403

    # Sensitivity policy: a restricted document cannot be shared with a whole role
    by_role = client.post(f"/api/documents/{document['id']}/share", headers=editor, json={"role": "viewer"})
    assert by_role.status_code == 400 and "restringidos" in by_role.json()["detail"]
    assert client.get(f"/api/documents/{document['id']}/download", headers=viewer2).status_code == 403
    # ...but it can be shared with lector2 by name
    client.post(f"/api/documents/{document['id']}/share", headers=editor, json={"username": "lector2"})
    assert client.get(f"/api/documents/{document['id']}/download", headers=viewer2).status_code == 200

    # Audit log records denied accesses
    audit = client.get("/api/audit?only_failed=true", headers=admin_headers).json()
    assert any(entry["action"] == "download" and not entry["success"] for entry in audit)

    # Owner deletes -> goes to the recycle bin (still encrypted, invisible to others)
    assert client.delete(f"/api/documents/{document['id']}", headers=editor).status_code == 204
    assert read_stored_ciphertext(document["id"]) is not None
    assert client.get(f"/api/documents/{document['id']}/download", headers=viewer).status_code == 404
    trash = client.get("/api/trash", headers=editor).json()
    assert [d["id"] for d in trash] == [document["id"]]
    # Purge -> the encrypted file is removed for good
    assert client.delete(f"/api/trash/{document['id']}", headers=editor).status_code == 204
    assert read_stored_ciphertext(document["id"]) is None


def test_bruteforce_lockout(client, admin_headers):
    client.post("/api/users", headers=admin_headers, json={"username": "victima", "password": "Clave123*", "role": "viewer"})
    for _ in range(config.MAX_FAILED_LOGINS):
        assert client.post("/api/auth/login", data={"username": "victima", "password": "mal"}).status_code == 401
    locked = client.post("/api/auth/login", data={"username": "victima", "password": "Clave123*"})
    assert locked.status_code == 423


def test_docx_extraction(client, admin_headers):
    import io

    from docx import Document as DocxDocument

    docx_buffer = io.BytesIO()
    word = DocxDocument()
    word.add_paragraph("Historia clínica del paciente con diagnóstico y fórmula médica de medicamentos.")
    word.save(docx_buffer)
    response = client.post("/api/documents/analyze", headers=admin_headers,
                           files={"file": ("historia.docx", docx_buffer.getvalue())})
    assert response.status_code == 200
    assert response.json()["category"] == "Salud"
    assert response.json()["sensitivity"] == "confidencial"
