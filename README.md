# Bóveda IA — Sistema de bodega de documentos encriptados con IA

**Avance: 40 %** · Python 3.10+ · FastAPI · SQLite · AES-256-GCM · scikit-learn

Plataforma para almacenar, organizar y proteger documentos digitales. Cada archivo se cifra antes de
guardarse, el acceso se controla por roles y permisos por documento, y un módulo de IA clasifica el
documento y detecta información sensible en el momento de subirlo.

---

## 1. Qué incluye este 40 %

| Módulo | Estado | Detalle |
|---|---|---|
| Autenticación | ✅ | Login con JWT, contraseñas con bcrypt, política de contraseñas, bloqueo tras 5 intentos fallidos (anti fuerza bruta) |
| Roles (RBAC) | ✅ | `admin` (todo), `editor` (sube, comparte, elimina lo suyo), `viewer`/lector (solo lo que le comparten) |
| Cifrado | ✅ | Cifrado de sobre AES-256-GCM: llave aleatoria por documento, envuelta con una llave maestra. Verificación de integridad con SHA-256 |
| Gestión de documentos | ✅ | Subir, listar, ver, descargar (descifrar), compartir con usuario o rol, revocar, eliminar |
| Bitácora de accesos | ✅ | Registra inicios de sesión, descargas, accesos denegados, cambios de permisos (IP, navegador, resultado) |
| IA: clasificación | ✅ | TF-IDF + Naive Bayes en 7 categorías: Financiero, Legal, Recursos Humanos, Salud, Técnico/TI, Académico, Administrativo |
| IA: datos sensibles | ✅ | Cédula, NIT (con dígito de verificación), tarjetas (algoritmo de Luhn), cuentas bancarias, correos, teléfonos, direcciones, contraseñas, fechas de nacimiento, datos de salud y datos sensibles de la Ley 1581 de 2012. Calcula un puntaje de riesgo y un nivel: público / interno / confidencial / restringido |
| Interfaz web | ✅ | Login, documentos, análisis con IA, usuarios y bitácora |
| Pruebas | ✅ | 9 pruebas automáticas con pytest |

### Pendiente (60 % restante)

- IA: **detección de accesos sospechosos** (modelo de anomalías, p. ej. Isolation Forest, sobre la bitácora que ya se está registrando: horarios inusuales, descargas masivas, IP nuevas, accesos denegados repetidos).
- IA: **búsqueda inteligente** (búsqueda semántica por similitud sobre las palabras clave y categorías ya calculadas).
- Reglas de acceso según nivel de sensibilidad, alertas al administrador, rotación de llave maestra, reentrenamiento del clasificador con documentos reales.

---

## 2. Arquitectura

```
Navegador (frontend/index.html — local o en Vercel)
        │  JWT
        ▼
FastAPI (app/main.py)
 ├── routers/auth.py        login, bloqueo por fuerza bruta
 ├── routers/users.py       usuarios, roles, bitácora
 └── routers/documents.py   subir / descargar / compartir / eliminar
        │
        ├── ai/text_extractor.py     txt, md, csv, pdf, docx → texto (solo en memoria)
        ├── ai/classifier.py         TF-IDF + Naive Bayes → categoría + palabras clave
        ├── ai/sensitive_detector.py regex + validadores → hallazgos enmascarados + riesgo
        ├── crypto/vault_crypto.py   AES-256-GCM, cifrado de sobre
        ├── services/permission_service.py  reglas de acceso
        └── services/audit_service.py       bitácora
        │
        ▼
data/vault.db (SQLite: metadatos, llaves envueltas, bitácora)
data/storage/*.enc (solo texto cifrado; en Render se guarda en la tabla encrypted_blobs)
data/master.key (llave maestra — NO se sube a ningún repositorio)
```

### Flujo al subir un documento

1. Se valida extensión (.txt, .md, .csv, .pdf, .docx) y tamaño (máx. 10 MB).
2. Se extrae el texto **en memoria** y la IA lo clasifica y busca datos sensibles.
3. Se genera una llave AES-256 aleatoria para ese documento y se cifra el archivo (AES-GCM).
4. La llave del documento se cifra con la llave maestra y solo esa versión cifrada se guarda en la BD.
5. En disco queda únicamente `data/storage/<id>.enc`. En la BD solo quedan los hallazgos **enmascarados** (`*******8901`), nunca el dato real.

El ID del documento se usa como *Associated Data* de AES-GCM: si alguien cambia el archivo cifrado o lo
intercambia con el de otro documento, el descifrado falla y la descarga se bloquea.

---

## 3. Instalación (Anaconda)

Abre **Anaconda Prompt** en la carpeta del proyecto:

```bash
conda create -n boveda python=3.11 -y
conda activate boveda
pip install -r requirements-dev.txt
```

## 4. Ejecución

**Opción A — Anaconda Prompt**

```bash
python run.py
```

**Opción B — Spyder**: abre `run.py` y presiona **F5**. El servidor queda corriendo en segundo plano;
para detenerlo, reinicia el kernel (Consola → Reiniciar kernel). En Spyder, selecciona el intérprete del
entorno `boveda` (Herramientas → Preferencias → Intérprete de Python).

Luego abre:

- Aplicación: <http://127.0.0.1:8000>
- Documentación interactiva de la API (Swagger): <http://127.0.0.1:8000/docs>

Usuario inicial: **admin** / **Admin123\*** (créalo distinto con las variables `VAULT_ADMIN_USER` y `VAULT_ADMIN_PASSWORD`).

## 5. Demostración sugerida

1. Entra como `admin`, ve a **Usuarios** y crea un `editor` y un `lector`.
2. En **Documentos**, sube los archivos de la carpeta `ejemplos/`. Cada uno queda clasificado y con nivel de sensibilidad:

| Archivo | Categoría | Sensibilidad |
|---|---|---|
| acta_reunion.txt | Administrativo | Público |
| propuesta_grado.docx | Académico | Público |
| historia_clinica.txt | Salud | Confidencial |
| certificado_laboral.txt | Recursos Humanos | Restringido |
| factura_proveedor.txt | Financiero | Restringido |
| configuracion_servidor.txt | Técnico / TI | Restringido |

3. Abre `data/storage/` y muestra que los archivos `.enc` son ilegibles.
4. Inicia sesión como el lector: no ve nada. Como admin, comparte un documento con él y vuelve a entrar: ahora puede descargarlo.
5. Intenta entrar 5 veces con una contraseña errada: la cuenta se bloquea. Revisa todo en **Bitácora** (filtro *Solo fallidos*).

## 6. Pruebas

```bash
python -m pytest -v
```

Para correrlas contra PostgreSQL en modo producción: define `VAULT_DATABASE_URL`, `VAULT_STORAGE_BACKEND=database`,
`VAULT_ENV=production`, `VAULT_MASTER_KEY`, `VAULT_JWT_SECRET` y `VAULT_ADMIN_PASSWORD` antes de ejecutar pytest.

Cubren: cifrado/descifrado, detección de manipulación, intercambio de archivos cifrados, validadores (Luhn,
NIT), enmascaramiento, flujo completo de roles y permisos, bloqueo por fuerza bruta y lectura de .docx.

## 7. API principal

| Método | Ruta | Rol |
|---|---|---|
| POST | `/api/auth/login` | público |
| GET | `/api/auth/me` | autenticado |
| GET / POST | `/api/users` | admin (GET también editor) |
| PATCH | `/api/users/{id}` | admin |
| GET | `/api/audit` | admin |
| POST | `/api/documents` | admin, editor |
| POST | `/api/documents/analyze` | autenticado |
| GET | `/api/documents` | autenticado (solo los accesibles) |
| GET | `/api/documents/{id}` · `/download` | con permiso de lectura |
| POST | `/api/documents/{id}/share` | con permiso de gestión |
| GET / DELETE | `/api/documents/{id}/permissions[/{pid}]` | con permiso de gestión |
| DELETE | `/api/documents/{id}` | con permiso de gestión (no lectores) |

## Despliegue en Render + Vercel

Ver **[DESPLIEGUE.md](DESPLIEGUE.md)**.

## 8. Configuración (variables de entorno opcionales)

| Variable | Uso | Por defecto |
|---|---|---|
| `VAULT_MASTER_KEY` | Llave maestra en base64 (32 bytes) | se genera en `data/master.key` |
| `VAULT_JWT_SECRET` | Secreto para firmar tokens | se genera en `data/jwt.secret` |
| `VAULT_DATA_DIR` | Carpeta de datos | `./data` |
| `VAULT_TOKEN_MINUTES` | Duración de la sesión | 60 |
| `VAULT_MAX_UPLOAD_MB` | Tamaño máximo de archivo | 10 |
| `VAULT_ENV` | `production` exige llaves y PostgreSQL definidos | `development` |
| `DATABASE_URL` | Conexión PostgreSQL (la pone Render) | SQLite local |
| `VAULT_STORAGE_BACKEND` | `disk` o `database` | `disk` (local) / `database` (producción) |
| `VAULT_CORS_ORIGINS` | Orígenes permitidos, separados por coma (URL de Vercel) | — |
| `VAULT_CORS_ORIGIN_REGEX` | Regex opcional para las vistas previas de Vercel | — |

> ⚠️ Si se pierde `data/master.key`, los documentos **no se pueden recuperar**. En producción, la llave
> maestra debería estar en un gestor de secretos (KMS, HashiCorp Vault, Azure Key Vault).

## 9. Limitaciones conocidas del prototipo

- El clasificador se entrena con un corpus semilla pequeño (`app/ai/training_data.py`, 84 ejemplos); su precisión mejora con documentos reales etiquetados.
- La detección de datos sensibles se basa en patrones; no reconoce nombres propios (eso requeriría un modelo NER, p. ej. spaCy).
- Los PDF escaneados (imágenes) no tienen texto extraíble sin OCR.
- El token se guarda solo en memoria del navegador: al recargar la página hay que iniciar sesión de nuevo.
