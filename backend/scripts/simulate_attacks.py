"""Demo: generate real suspicious activity against the API to see the detector working.

    python scripts/simulate_attacks.py                         # local API (http://127.0.0.1:8000)
    python scripts/simulate_attacks.py --api https://boveda-ia-api.onrender.com --admin-password XXXX

Scenarios (all of them are real HTTP requests, recorded in the access log):
  1. Brute force: 5 wrong passwords for "demo_victima"            -> brute_force (crítica) + account lock
  2. Mass download: "demo_editor" downloads 12 times in a row     -> mass_download + downloads paused
  3. Access denied: "demo_lector" tries a document without access  -> access_denied
  4. Enumeration: "demo_lector" runs 26 searches in a few seconds  -> enumeration
  5. (optional, --ip) failures with 3 usernames from your IP       -> credential_stuffing + IP blocked 15 min
     Warning: it blocks logins from YOUR IP for 15 minutes, including the admin.
Then it prints the alerts raised. Open "Alertas de seguridad" in the web app to review them.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx

DEMO_PASSWORD = "Demo#2026x"
EXAMPLES = Path(__file__).resolve().parents[2] / "ejemplos"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--admin-user", default="admin")
    parser.add_argument("--admin-password", default="Admin123*")
    parser.add_argument("--ip", action="store_true", help="incluir el escenario de ataque desde una IP (bloquea tu IP 15 min)")
    args = parser.parse_args()
    api = httpx.Client(base_url=args.api.rstrip("/"), timeout=90)

    def login(username: str, password: str) -> dict:
        response = api.post("/api/auth/login", data={"username": username, "password": password})
        if response.status_code != 200:
            sys.exit(f"No se pudo iniciar sesión como {username}: {response.text}")
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    print(f"→ API: {args.api}")
    admin = login(args.admin_user, args.admin_password)
    users = {u["username"]: u for u in api.get("/api/users", headers=admin).json()}
    for username, role in (("demo_editor", "editor"), ("demo_lector", "viewer"), ("demo_victima", "viewer")):
        if username not in users:
            api.post("/api/users", headers=admin, json={"username": username, "password": DEMO_PASSWORD, "role": role})
        else:  # leave them ready for a new run
            api.post(f"/api/users/{users[username]['id']}/unblock", headers=admin)

    editor = login("demo_editor", DEMO_PASSWORD)
    viewer = login("demo_lector", DEMO_PASSWORD)
    sample = EXAMPLES / "certificado_laboral.txt"
    document = api.post("/api/documents", headers=editor, files={"file": (sample.name, sample.read_bytes())}).json()
    print(f"→ Documento de prueba: {document['original_name']} ({document['sensitivity']})")

    print("1. Fuerza bruta contra demo_victima…")
    for _ in range(5):
        api.post("/api/auth/login", data={"username": "demo_victima", "password": "adivinando"})

    print("2. Descarga masiva de demo_editor…")
    codes = [api.get(f"/api/documents/{document['id']}/download", headers=editor).status_code for _ in range(12)]
    print(f"   respuestas: {codes.count(200)} descargas permitidas, {codes.count(429)} bloqueadas por la respuesta automática")

    print("3. Accesos denegados de demo_lector…")
    for _ in range(4):
        api.get(f"/api/documents/{document['id']}/download", headers=viewer)

    print("4. Exploración masiva de demo_lector…")
    for word in ["factura", "cedula", "salario", "contrato", "clave", "cuenta"] * 4 + ["nomina", "paciente"]:
        api.get("/api/search", params={"q": word}, headers=viewer)

    if args.ip:
        print("5. Ataque de credenciales desde tu IP (quedará bloqueada 15 minutos)…")
        for name in ("root", "soporte", "contabilidad"):
            api.post("/api/auth/login", data={"username": name, "password": "123456"})

    print("\nAlertas generadas:")
    for alert in api.get("/api/alerts", headers=admin, params={"status": "activas"}).json()[:15]:
        response = f"  → {alert['response']}" if alert["response"] else ""
        print(f"  [{alert['severity'].upper():8}] {alert['title']}{response}")
    print("\nRevísalas en la aplicación: Administración → Alertas de seguridad.")


if __name__ == "__main__":
    main()
