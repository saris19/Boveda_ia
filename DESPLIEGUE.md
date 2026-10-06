# Despliegue: API en Render + Frontend en Vercel

```
Usuario ──► Vercel (frontend/index.html + config.js)
               │  fetch + JWT (CORS)
               ▼
            Render Web Service (FastAPI)  ──►  Render PostgreSQL
                                               (metadatos + archivos cifrados)
```

- **Render** ejecuta la API. Su disco es efímero (se borra al reiniciar), así que en producción los
  archivos cifrados se guardan en PostgreSQL (`VAULT_STORAGE_BACKEND=database`).
- **Vercel** sirve solo la carpeta `frontend/` (HTML estático). `frontend/config.js` le dice dónde está la API.
- Con `VAULT_ENV=production`, la API **no arranca** si faltan la llave maestra, el secreto JWT, la contraseña
  del admin o PostgreSQL. Así se evita perder documentos por una llave generada al azar.

Necesitas cuentas gratuitas en **GitHub**, **Render** y **Vercel** (puedes entrar a Render y Vercel con GitHub).

---

## Paso 1 — Subir el proyecto a GitHub

1. En github.com → **New repository** → nombre `boveda-ia` → *Private* → **Create** (sin README).
2. En la Terminal, dentro de la carpeta del proyecto:

```bash
cd ~/Downloads/boveda-ia
git init
git add .
git commit -m "Bóveda IA: avance 40% + configuración de despliegue"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/boveda-ia.git
git push -u origin main
```

> `.gitignore` excluye la carpeta `data/`: tu `master.key` local **nunca** se sube.
> Comprueba con `git status` que no aparezca `data/` antes del commit.

## Paso 2 — Crear la API y la base de datos en Render

1. render.com → **New +** → **Blueprint** → conecta GitHub y elige el repo `boveda-ia`.
2. Render lee `render.yaml` y propone crear:
   - `boveda-ia-api` (Web Service, plan Free)
   - `boveda-ia-db` (PostgreSQL, plan Free)
3. Te pedirá dos valores:
   - `VAULT_ADMIN_PASSWORD`: contraseña del usuario `admin` (mín. 8 caracteres, con mayúscula, minúscula, número y símbolo).
   - `VAULT_CORS_ORIGINS`: por ahora escribe `https://boveda-ia.vercel.app` (lo corriges en el paso 5).
4. **Apply**. La primera compilación tarda unos minutos.
5. Cuando diga *Live*, abre `https://boveda-ia-api.onrender.com/api/health` (usa la URL real que te muestre
   Render; si el nombre ya estaba ocupado le agrega un sufijo). Debe responder `{"status":"ok",...}`.
   La documentación interactiva queda en `/docs`.
6. **Respalda la llave maestra**: servicio `boveda-ia-api` → **Environment** → copia el valor de
   `VAULT_MASTER_KEY` y guárdalo en un lugar seguro. Sin ella los documentos no se pueden descifrar.

## Paso 3 — Apuntar el frontend a tu API

Edita `frontend/config.js` con la URL real de Render (sin `/` al final):

```js
window.VAULT_API_URL = "https://boveda-ia-api.onrender.com";
```

```bash
git add frontend/config.js
git commit -m "Configura URL de la API"
git push
```

## Paso 4 — Publicar el frontend en Vercel

1. vercel.com → **Add New…** → **Project** → importa el repo `boveda-ia`.
2. Configura:
   - **Root Directory**: `frontend`  ← importante
   - **Framework Preset**: `Other`
   - Build Command y Output Directory: vacíos
3. **Deploy**. Copia la URL de producción, por ejemplo `https://boveda-ia.vercel.app`.

## Paso 5 — Autorizar a Vercel en la API (CORS)

En Render → `boveda-ia-api` → **Environment**:

- `VAULT_CORS_ORIGINS` = la URL exacta de Vercel (sin `/` final). Si tienes varias, sepáralas con coma.
- (Opcional) `VAULT_CORS_ORIGIN_REGEX` = `https://boveda-ia-.*\.vercel\.app` para permitir las vistas previas de Vercel.

**Save Changes** → Render redepliega solo.

## Paso 6 — Probar

1. Abre la URL de Vercel e inicia sesión con `admin` y la contraseña del paso 2.
2. Sube los archivos de `ejemplos/`, crea usuarios, comparte y revisa la Bitácora.

---

## Cosas a tener en cuenta (plan gratuito)

| Tema | Qué pasa | Qué hacer |
|---|---|---|
| La API "se duerme" | Tras 15 min sin tráfico, Render apaga el servicio; el primer acceso tarda ~1 min | Normal. El botón de login muestra "Despertando el servidor…". Ábrela unos minutos antes de presentar |
| PostgreSQL gratis vence | Expira 30 días después de crearla (14 días de gracia para pasar a plan pago) | Suficiente para la entrega. Para más tiempo, usa una base externa (p. ej. Neon) y pon su URL en `DATABASE_URL` |
| Tamaño de la BD | 1 GB | Más que suficiente con archivos de hasta 10 MB |
| Llave maestra | Si se pierde o se cambia, los documentos existentes no se pueden abrir | Respáldala (paso 2.6). No borres ni regeneres `VAULT_MASTER_KEY` |

## Solución de problemas

| Síntoma | Causa probable |
|---|---|
| "No se pudo conectar con el servidor" en Vercel | URL equivocada en `frontend/config.js`, o falta la URL de Vercel en `VAULT_CORS_ORIGINS` |
| En la consola del navegador: `blocked by CORS policy` | `VAULT_CORS_ORIGINS` no coincide exactamente (https, sin `/` final) |
| El deploy en Render falla con "Faltan variables de entorno obligatorias" | Falta `VAULT_ADMIN_PASSWORD` u otra variable en Environment |
| Login de `admin` no funciona | La contraseña se fija **solo** cuando la base está vacía. Si la cambiaste después en Render, sigue valiendo la primera |
| Error 409 "Falla de integridad" al descargar | `VAULT_MASTER_KEY` cambió respecto a la que cifró el documento |
