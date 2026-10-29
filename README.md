# Bóveda IA — Sistema de bodega de documentos encriptados con IA

**Versión 1.0 · Avance: 100 %** · Backend: Python + FastAPI · Frontend: React + Vite · AES-256-GCM · scikit-learn

Plataforma para almacenar, organizar y proteger documentos digitales. Cada archivo se cifra antes de
guardarse, el acceso se controla por roles, permisos por documento y nivel de sensibilidad, y la
inteligencia artificial clasifica los documentos, detecta información sensible, permite **buscar dentro de
los archivos cifrados** y **detecta accesos sospechosos**.

```
boveda-ia/
├── backend/     API REST (FastAPI) → Render
│   ├── app/ai/         clasificador, datos sensibles, índice ciego, detector de anomalías
│   ├── app/crypto/     cifrado AES-256-GCM y llavero con rotación
│   ├── app/routers/    endpoints (documentos, búsqueda, alertas, papelera, administración…)
│   ├── app/services/   permisos, políticas, alertas, bitácora, almacenamiento
│   ├── scripts/simulate_attacks.py   demostración de ataques reales contra la API
│   └── tests/          22 pruebas automáticas
├── frontend/    Interfaz web (React + Vite) → Vercel
├── ejemplos/    Documentos de prueba para la demostración
├── render.yaml  Blueprint de Render (API + PostgreSQL)
└── DESPLIEGUE.md
```

---

## 1. Funcionalidades

| Módulo | Detalle |
|---|---|
| Autenticación | JWT, contraseñas con bcrypt, política de contraseñas, bloqueo tras 5 intentos fallidos |
| Roles (RBAC) | `admin` (todo), `editor` (sube, comparte, elimina lo suyo), `viewer`/lector (solo lo que le comparten) |
| **Políticas por sensibilidad** | Confidencial: no se comparte con todo el rol Lector. Restringido: solo con usuarios con nombre propio. Se aplican al instante si la sensibilidad cambia |
| Cifrado | Cifrado de sobre AES-256-GCM: llave aleatoria por documento y por versión; integridad SHA-256; datos asociados que impiden intercambiar archivos cifrados |
| **Llavero y rotación** | Llave raíz (entorno) → llave maestra versionada (BD) → llave de cada documento. Rotar re-envuelve todas las llaves sin tocar el contenido cifrado |
| Gestión documental | Subir, listar, descargar, compartir, revocar |
| **Versiones** | Historial cifrado de cada documento; descargar o restaurar cualquier versión sin perder el historial |
| **Papelera** | Borrado suave con restauración durante 30 días y purga automática de todas las versiones |
| IA: clasificación | TF-IDF de palabras y caracteres + regresión logística en 7 categorías (exactitud por validación cruzada ≈ 71 %) |
| **IA: aprendizaje con correcciones** | Las personas corrigen la categoría; el modelo se reentrena con esas correcciones (guardando solo palabras comunes, sin nombres ni números) |
| IA: datos sensibles | Cédula, NIT, tarjetas (Luhn), cuentas, correos, teléfonos, direcciones, contraseñas, salud, Ley 1581 de 2012; valores enmascarados |
| IA: búsqueda inteligente | Busca dentro del contenido cifrado con un índice ciego HMAC; tolera plurales y errores; entiende la intención de la búsqueda |
| **IA: accesos sospechosos** | 7 reglas explicables + modelo **Isolation Forest** sobre la bitácora, con alertas, gestión de estados y respuestas automáticas |
| Panel e interfaz | Indicadores, gráficas, centro de seguridad, tema claro/oscuro, versión celular |
| Bitácora | Todas las acciones con usuario, IP, resultado y detalle |

---

## 2. Detección de accesos sospechosos

Cada evento de la bitácora pasa por dos capas justo después de registrarse:

**Reglas** (ataques conocidos, fáciles de explicar):

| Regla | Condición | Severidad | Respuesta automática |
|---|---|---|---|
| Fuerza bruta | ≥ 3 inicios fallidos del mismo usuario en 10 min | alta / crítica (≥ 5) | Cuenta bloqueada 15 min |
| Ataque desde una IP | Una IP falla con ≥ 3 usuarios distintos en 10 min | crítica | IP bloqueada para iniciar sesión 15 min |
| Descarga masiva | ≥ 10 descargas en 10 min | alta / crítica (si hay restringidos) | Descargas del usuario pausadas 15 min |
| Accesos denegados | ≥ 3 intentos sin permiso en 10 min | media / alta | — |
| Fuera de horario | Documento confidencial o restringido entre 22:00 y 06:00 | media | — |
| IP nueva | Inicio de sesión desde una IP nunca usada | baja | — |
| Exploración masiva | ≥ 25 búsquedas o consultas en 5 min | media | — |

**Modelo de IA (Isolation Forest, 200 árboles)**: convierte cada evento en 12 variables de comportamiento
(hora, fin de semana, tipo de acción, fallos, acciones en 10 min, descargas y documentos distintos en 1 h,
IP nueva, sensibilidad del documento, desvío del horario habitual del usuario) y marca como anómalo lo
que se aleja del comportamiento normal (puntaje ≥ 60/100). Cada alerta explica qué variables la causaron.
Arranca con una línea base sintética de comportamiento normal (arranque en frío) y se reentrena con la
bitácora real cada 200 eventos o cuando el administrador lo pida.

Las alertas iguales en 30 minutos se agrupan (no inundan el panel) y el administrador las marca como
*en revisión*, *resueltas* o *falso positivo*.

**Demostración:** con la API encendida, en otra terminal:

```bash
cd backend
python scripts/simulate_attacks.py
```

Hace peticiones reales (fuerza bruta, descarga masiva, accesos denegados y exploración) y muestra las
alertas generadas. Contra Render: `python scripts/simulate_attacks.py --api https://boveda-ia-api.onrender.com --admin-password TU_CLAVE`.

---

## 3. Búsqueda inteligente (índice ciego)

El texto de los documentos nunca se guarda. Cada palabra relevante se normaliza (`facturas → factur`) y se
transforma con HMAC-SHA256 usando una llave derivada de la llave raíz. Al buscar, las palabras de la
consulta pasan por la misma transformación. La relevancia combina contenido cifrado (55 %), metadatos con
tolerancia a errores (35 %) e intención detectada por el clasificador (10 %).

---

## 4. Ejecutar en tu computador

Necesitas **Python 3.10+** (Anaconda sirve) y **Node.js 18+**. Usa dos terminales.

**Terminal 1 — API**

```bash
cd backend
conda create -n boveda python=3.11 -y     # solo la primera vez
conda activate boveda
pip install -r requirements-dev.txt        # solo la primera vez
python run.py
```

API en <http://127.0.0.1:8000> y documentación interactiva en <http://127.0.0.1:8000/docs>.

**Terminal 2 — Interfaz web**

```bash
cd frontend
npm install        # solo la primera vez
npm run dev
```

Abre <http://localhost:5173>. Usuario inicial: **admin** / **Admin123\***.

## 5. Guion de demostración

1. **Usuarios y roles:** crea un editor y un lector.
2. **Documentos:** sube los archivos de `ejemplos/`. Cada uno queda cifrado, clasificado y con nivel de sensibilidad.
3. **Detalle de un documento:** sube una nueva versión, corrige la clasificación y comparte. Observa que un
   documento restringido no se puede compartir con un rol completo.
4. **Búsqueda inteligente:** `losartán` (palabra solo dentro del archivo), `facturas`, `certificdo`, `pago a proveedores`.
5. **Ataques:** ejecuta `python scripts/simulate_attacks.py` y abre **Alertas de seguridad**: verás fuerza
   bruta, descarga masiva con descargas pausadas, accesos denegados, exploración y anomalías de la IA.
6. **Usuarios y roles:** los usuarios afectados muestran *Cuenta bloqueada* o *Descargas pausadas* y se pueden desbloquear.
7. **Centro de seguridad:** rota la llave maestra y comprueba que todo se sigue descargando.
8. **Papelera:** envía un documento a la papelera y restáuralo.

## 6. Pruebas

```bash
cd backend
python -m pytest -v
```

22 pruebas: cifrado y manipulación, validadores, enmascaramiento, roles y permisos, políticas por
sensibilidad, fuerza bruta, versiones, papelera, correcciones y reentrenamiento, rotación de llaves,
índice ciego y búsqueda, panel, migraciones, reglas de detección, respuestas automáticas, modelo
Isolation Forest y gestión de alertas. También pasan contra PostgreSQL en modo producción.

## 7. API principal

| Método | Ruta | Rol |
|---|---|---|
| POST | `/api/auth/login` | público |
| GET | `/api/stats` · `/api/search` | autenticado |
| GET / POST | `/api/documents` | autenticado / admin, editor |
| GET | `/api/documents/{id}/download` | permiso de lectura |
| GET / POST | `/api/documents/{id}/versions` | lectura / gestión |
| GET · POST | `/api/documents/{id}/versions/{n}/download` · `/restore` | lectura · gestión |
| PATCH | `/api/documents/{id}/classification` | gestión (admin, editor) |
| POST · DELETE | `/api/documents/{id}/share` · `/permissions/{pid}` | gestión |
| DELETE | `/api/documents/{id}` (a la papelera) | gestión |
| GET · POST · DELETE | `/api/trash` · `/api/trash/{id}/restore` · `/api/trash/{id}` | propietario, admin |
| GET · PATCH | `/api/alerts` · `/api/alerts/summary` · `/api/alerts/{id}` | admin |
| POST | `/api/alerts/model/retrain` | admin |
| GET · POST | `/api/admin/security` · `/api/admin/rotate-key` · `/api/admin/classifier/retrain` | admin |
| GET / POST / PATCH | `/api/users` · `/api/users/{id}` · `/api/users/{id}/unblock` | admin |
| GET | `/api/audit` | admin |

## 8. Configuración del backend (variables de entorno)

| Variable | Uso | Por defecto |
|---|---|---|
| `VAULT_MASTER_KEY` | Llave raíz en base64 (32 bytes) | se genera en `backend/data/master.key` |
| `VAULT_JWT_SECRET` | Secreto para firmar tokens | se genera en `backend/data/jwt.secret` |
| `VAULT_ADMIN_USER` / `VAULT_ADMIN_PASSWORD` | Administrador inicial | `admin` / `Admin123*` |
| `VAULT_ENV` | `production` exige llaves y PostgreSQL definidos | `development` |
| `DATABASE_URL` | Conexión PostgreSQL (la pone Render) | SQLite local |
| `VAULT_STORAGE_BACKEND` | `disk` o `database` | `disk` local / `database` producción |
| `VAULT_CORS_ORIGINS` · `VAULT_CORS_ORIGIN_REGEX` | Orígenes del frontend permitidos | — |
| `VAULT_TIMEZONE` | Zona horaria para la regla de horario | `America/Bogota` |
| `VAULT_OFF_HOURS_START` · `VAULT_OFF_HOURS_END` | Horario no laboral | 22 · 6 |
| `VAULT_TRASH_DAYS` | Días en la papelera | 30 |
| `VAULT_DOWNLOAD_BLOCK_MINUTES` | Pausa de descargas tras descarga masiva | 15 |
| `VAULT_TOKEN_MINUTES` · `VAULT_MAX_UPLOAD_MB` | Duración de sesión · tamaño máximo | 60 · 10 |

> ⚠️ Si se pierde la llave raíz (`VAULT_MASTER_KEY`), los documentos **no se pueden recuperar**.

## 9. Despliegue

API en Render y frontend en Vercel: ver **[DESPLIEGUE.md](DESPLIEGUE.md)**. Las bases de datos de
versiones anteriores se actualizan solas al arrancar (migraciones automáticas).

## 10. Limitaciones conocidas

- El clasificador parte de 210 ejemplos semilla; mejora con las correcciones de los usuarios.
- La detección de datos sensibles se basa en patrones; no reconoce nombres propios (requeriría un modelo NER).
- Los PDF escaneados no tienen texto extraíble sin OCR.
- El modelo de anomalías vive en memoria: se reentrena al arrancar y periódicamente desde la bitácora.
- El índice ciego revela si dos documentos comparten una palabra (no cuál) a quien acceda a la base de datos.
