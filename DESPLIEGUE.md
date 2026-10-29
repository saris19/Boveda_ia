# Despliegue: API en Render + Frontend en Vercel

```
Usuario ──► Vercel: frontend/ (React compilado, HTML/JS/CSS estáticos)
               │  fetch + JWT  (CORS solo para tu dominio de Vercel)
               ▼
            Render Web Service: backend/ (FastAPI)  ──►  Render PostgreSQL
                                                         (metadatos, índice ciego y archivos cifrados)
```

| Pieza | Carpeta | Dónde | URL |
|---|---|---|---|
| API | `backend/` | Render (Blueprint `render.yaml`) | https://boveda-ia-api.onrender.com |
| Interfaz | `frontend/` | Vercel (Vite) | https://boveda-ia.vercel.app |

---

## Paso 1 — Actualizar el repositorio con la versión final (1.0)

Descomprime el zip nuevo **aparte** y copia su contenido sobre tu repositorio (si Descargas le cambió el
nombre al zip, por ejemplo `boveda-ia-v100 (1).zip`, usa ese nombre):

```bash
cd ~/Downloads
unzip -o boveda-ia-v100.zip -d boveda-v100
cd boveda-ia
git rm -r -q --ignore-unmatch app tests frontend run.py requirements.txt requirements-dev.txt
cp -R ../boveda-v100/boveda-ia/. .
git add -A
git status
```

En `git status` deben aparecer `backend/` y `frontend/` y **no** debe aparecer ninguna carpeta `data/` ni
`node_modules/`. Luego:

```bash
git commit -m "Versión 1.0: accesos sospechosos, versiones, papelera, políticas y rotación de llaves"
git push
```

## Paso 2 — Render (API)

Tu Blueprint `boveda-ia` está conectado al repositorio: al hacer `push`, Render lee el `render.yaml`
nuevo y aplica los cambios solo (ahora la API está en `backend/` gracias a `rootDir: backend`).

1. Entra a **boveda-ia-api → Events** y espera el nuevo deploy. Si no arranca solo, usa
   **Manual Deploy → Deploy latest commit**.
2. En **Environment** verifica que existan estas variables (el Blueprint las crea):
   `DATABASE_URL`, `VAULT_ENV`, `VAULT_STORAGE_BACKEND`, `VAULT_MASTER_KEY`, `VAULT_JWT_SECRET`,
   `VAULT_ADMIN_PASSWORD`, `VAULT_CORS_ORIGINS`, `VAULT_CORS_ORIGIN_REGEX`, `PYTHON_VERSION`.
3. **Contraseña del admin:** si no la definiste tú, Render la generó. Haz clic en el ojo junto a
   `VAULT_ADMIN_PASSWORD` para verla y cópiala. Es la contraseña del usuario `admin`.
4. **Respalda `VAULT_MASTER_KEY`** en un lugar seguro: sin ella los documentos no se pueden descifrar.
5. Prueba: <https://boveda-ia-api.onrender.com/api/health> debe responder `{"status":"ok","version":"1.0.0"}`.

> Si la base de datos ya tenía tablas de una versión anterior, la API agrega sola las columnas y tablas
> nuevas al arrancar (versiones, papelera, llavero, alertas). No hay que borrar nada: los documentos
> existentes se siguen descargando.

## Paso 3 — Vercel (interfaz)

En tu proyecto `boveda-ia` de Vercel → **Settings → Build and Deployment**:

| Opción | Valor |
|---|---|
| Root Directory | `frontend` |
| Framework Preset | `Vite` |
| Build Command | `npm run build` (o vacío, lo toma de `vercel.json`) |
| Output Directory | `dist` |
| Install Command | vacío (usa `npm install`) |

Guarda y ve a **Deployments → ⋯ → Redeploy**.

La URL de la API viene en `frontend/.env.production` (`VITE_API_URL`). No hace falta configurar variables
en Vercel. Si tu API tuviera otra URL, cambia ese archivo **y** la línea `connect-src` de
`frontend/vercel.json` (la política de seguridad solo deja conectar con esa API).

## Paso 3b — Si ya tenías el proyecto en el 50 %

Si en el repositorio ya estaban `backend/` y `frontend/`, el Paso 1 basta: Render y Vercel redespliegan
solos al recibir el `push`. No hay que cambiar ninguna configuración.

## Paso 4 — Probar

1. Abre <https://boveda-ia.vercel.app>. Debajo del botón *Entrar* verás el estado del servidor:
   - "Despertando el servidor…": el plan gratuito de Render se duerme tras 15 min; espera hasta 1 minuto.
   - "Servidor en línea": ya puedes entrar.
2. Entra con `admin` y la contraseña del paso 2.3.
3. Sigue el guion de demostración del README.
4. Para ver la detección de ataques sobre la versión publicada, desde tu computador:

   ```bash
   cd backend
   python scripts/simulate_attacks.py --api https://boveda-ia-api.onrender.com --admin-password LA_CLAVE_DEL_ADMIN
   ```

   Luego abre **Alertas de seguridad** en la aplicación.

---

## Qué protege esta configuración

- **CORS**: la API solo acepta llamadas de `https://boveda-ia.vercel.app` y de las vistas previas de tu
  equipo de Vercel (`VAULT_CORS_ORIGIN_REGEX`).
- **Cabeceras de seguridad en Vercel**: Content-Security-Policy (solo scripts propios y conexión solo a tu
  API), HSTS, X-Frame-Options, nosniff, Referrer-Policy y Permissions-Policy.
- **Producción estricta**: con `VAULT_ENV=production` la API no arranca sin llave maestra, secreto JWT,
  contraseña de admin y PostgreSQL.

## Límites del plan gratuito

| Tema | Qué pasa | Qué hacer |
|---|---|---|
| La API se duerme | Tras 15 min sin tráfico; el primer acceso tarda ~1 min | Abre la página unos minutos antes de presentar |
| PostgreSQL gratis vence | 30 días después de crearla (14 de gracia) | Suficiente para la entrega; luego usa una base externa (p. ej. Neon) en `DATABASE_URL` |
| Llave maestra | Si cambia, los documentos existentes no se pueden abrir | No borres ni regeneres `VAULT_MASTER_KEY` |

## Solución de problemas

| Síntoma | Causa probable |
|---|---|
| Vercel muestra "FUNCTION_INVOCATION_FAILED" o 404 | Root Directory no es `frontend` o el preset no es Vite |
| "No se pudo contactar el servidor" | La API está caída o dormida: revisa Render → Logs |
| Consola del navegador: `blocked by CORS policy` | La URL de Vercel no coincide con `VAULT_CORS_ORIGINS` (https, sin `/` final) |
| Consola: `violates Content Security Policy` | La URL de la API no coincide con `connect-src` en `frontend/vercel.json` |
| Render: "Faltan variables de entorno obligatorias" | Falta alguna variable del paso 2.2 |
| Render: "Could not open requirements file" | El servicio no tiene `rootDir: backend`: haz Manual sync del Blueprint |
| Login de `admin` falla | La contraseña se fija solo la primera vez que la base está vacía |
| Error 409 "Falla de integridad" al descargar | `VAULT_MASTER_KEY` cambió respecto a la que cifró el documento |
