# Despliegue en Vercel (con base en Neon)

Guía para publicar ImprontIA con una URL pública y HTTPS, sin costo, en **Vercel** (plan Hobby).
Se crean **dos proyectos de Vercel a partir del mismo repositorio**:

| Proyecto | Carpeta raíz | Qué es | URL de ejemplo |
|---|---|---|---|
| `improntia-api` | `mvp/backend` | La API (FastAPI), que corre como una función de Vercel | `https://improntia-api.vercel.app` |
| `improntia-dashboard` | `mvp/dashboard` | El dashboard (React + Vite): la URL que se abre para usar ImprontIA | `https://improntia-dashboard.vercel.app` |

La base de datos es **PostgreSQL en Neon**. Se crea desde Vercel, en la sección Storage. Vercel no tiene una base propia.

> Alternativa: la guía `despliegue.md` cubre Docker local y Render. El código es el mismo en las tres opciones;
> lo específico de Vercel es `mvp/backend/vercel.json`, `mvp/backend/.python-version`,
> `mvp/backend/scripts/vercel_build.py` y `mvp/dashboard/vercel.json`.

---

## Qué cambia respecto de Render

- **Migraciones en el build, no en cada arranque.** Vercel arranca la función en frío cuando hace falta, y
  cada arranque vuelve a importar la app. Con `MIGRATE_ON_STARTUP=0`, la app no migra al arrancar. Las migraciones y los
  docentes de `SEED_TEACHERS` se aplican **una vez por despliegue**, en el build (`scripts/vercel_build.py`).
  La purga de sesiones vencidas (RNF10) sigue corriendo al arrancar porque es una sola consulta.
- **PDF del enunciado de hasta 4 MB** (antes 10 MB). Vercel corta cualquier pedido o respuesta de más de 4,5 MB.
- **Arranque en frío.** Después de un rato sin uso, el primer pedido tarda unos segundos mientras carga
  scikit-learn. Los siguientes van normal. En el plan gratis de Render, el servicio se duerme y tarda alrededor de un minuto.
- **Pool de conexiones chico.** Cada instancia de la función abre sus propias conexiones. Por eso se usa la URL
  *pooled* de Neon y `DB_POOL_SIZE=1`.

---

## Paso 0 — El código tiene que estar en GitHub

Vercel despliega desde GitHub. Primero hay que subir la rama y mergearla a `main`:

```bash
git push -u origin deploy-vercel
```

Después, en GitHub, se abre el pull request de `deploy-vercel` a `main` y se mergea.

## Paso 1 — Cuenta de Vercel

1. Entrar a <https://vercel.com/signup> y elegir **Continue with GitHub**. Usar la misma cuenta que es dueña del
   repositorio `ImprontIA-PFI`, o una que tenga acceso a él.
2. Cuando GitHub lo pida, dar acceso a Vercel al repositorio `ImprontIA-PFI` (basta con ese).

## Paso 2 — Proyecto de la API

1. En Vercel: **Add New… → Project** → elegir `ImprontIA-PFI` → **Import**.
2. **Project Name:** `improntia-api`.
3. **Root Directory:** **Edit** → elegir `mvp/backend`. Vercel detecta **FastAPI** solo.
4. **No** hacer clic en Deploy todavía: primero va la base (Paso 3) y las variables (Paso 4).
   Si ya se desplegó por error, no pasa nada: el build falla con "falta DATABASE_URL" y se vuelve a desplegar al final.

## Paso 3 — Base de datos (Neon, gratis)

1. En el proyecto `improntia-api`: pestaña **Storage → Create Database → Neon (Serverless Postgres)** →
   **Continue**. Región: **Washington, D.C. (iad1)**, la más cercana a la región por defecto de las funciones de Vercel.
   Plan **Free** → **Create**.
2. Cuando pregunte a qué proyecto conectarla: `improntia-api`, en **todos los entornos**.
3. Vercel crea sola la variable `DATABASE_URL`, que apunta a la URL *pooled* de Neon (el host termina en `-pooler…`).
   No hay que copiarla a mano.
   - Si la base se creó directamente en <https://neon.com>, copiar la cadena con **Connection pooling**
     activado y cargarla a mano como `DATABASE_URL` en el Paso 4.

## Paso 4 — Variables de la API

En `improntia-api` → **Settings → Environment Variables**, cargar estas variables para **Production y Preview**:

| Variable | Valor |
|---|---|
| `IMPRONTIA_ENV` | `production` |
| `JWT_SECRET` | un secreto propio de 48 caracteres o más: `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `MIGRATE_ON_STARTUP` | `0` |
| `SEED_TEACHERS` | docentes iniciales, `mail:clave` separados por coma. Por ejemplo: `mhackbartt@uade.edu.ar:<clave>,jferreira@uade.edu.ar:<clave>` |
| `DB_POOL_SIZE` | `1` |
| `DB_POOL_MAX` | `12` |
| `CORS_ORIGINS` | por ahora `http://localhost:5173`. Se corrige en el Paso 6 con la URL real del dashboard |
| `DATABASE_URL` | ya la creó el Paso 3; cargarla a mano solo si la base se hizo en neon.com |

Después: pestaña **Deployments → ⋯ → Redeploy** (o **Deploy**, si nunca se desplegó).

**Comprobación:** abrir `https://<url-de-la-api>/health`. Tiene que mostrar
`{"status":"ok","version":"1.0.0","commit":"…"}`. En el log del build se ven las líneas
"Migraciones aplicadas…" y "Docentes creados desde SEED_TEACHERS…".

## Paso 5 — Proyecto del dashboard

1. **Add New… → Project** → el mismo repositorio → **Import**.
2. **Project Name:** `improntia-dashboard`. **Root Directory:** `mvp/dashboard`. Vercel detecta **Vite**.
3. **Environment Variables** (en la misma pantalla):
   - `VITE_API_URL` = la URL de la API del Paso 4, sin barra final (p. ej. `https://improntia-api.vercel.app`).
4. **Deploy**.

`VITE_API_URL` queda grabada al compilar. Si la URL de la API cambia, hay que redesplegar el dashboard.

## Paso 6 — Conectar la API con el dashboard (CORS)

1. Copiar la URL de producción del dashboard. Es la que figura en **Domains** del proyecto, p. ej. `https://improntia-dashboard.vercel.app`.
2. En `improntia-api` → **Settings → Environment Variables** → editar `CORS_ORIGINS` con esa URL, sin barra final.
3. `improntia-api` → **Deployments → ⋯ → Redeploy**.

## Paso 7 — Verificar

1. Abrir la URL del dashboard e iniciar sesión con un docente de `SEED_TEACHERS`.
2. Crear una evaluación, abrir el código de acceso en otra ventana como estudiante, rendirla y finalizarla.
3. Opcional, desde la raíz del repositorio:
   ```bash
   python mvp/scripts/verificar_despliegue.py --api https://<url-de-la-api> \
       --email <docente> --clave '<clave>' --origen https://<url-del-dashboard>
   ```

---

## Problemas frecuentes

| Síntoma | Causa y solución |
|---|---|
| El build de la API falla con "falta DATABASE_URL" | No está la variable en ese entorno (Production o Preview). Cargarla y redesplegar. |
| Error de **CORS** en la consola del navegador | `CORS_ORIGINS` no coincide exactamente con la URL del dashboard (revisar `https://` y que no haya barra final). Corregir y redesplegar la API. |
| El dashboard no conecta ("Failed to fetch") | `VITE_API_URL` está mal o falta. Corregir y **redesplegar el dashboard**. |
| `413` al subir el enunciado | El PDF pesa más de 4 MB. Comprimirlo, por ejemplo con "Reducir tamaño" en Vista Previa. |
| El primer pedido tarda varios segundos | Es el arranque en frío de la función. Antes de una demo conviene abrir `/health` una vez. |
| Recargar una página interna del dashboard da 404 | Falta la regla de `mvp/dashboard/vercel.json` que redirige todas las rutas a `index.html`. Revisar que la Root Directory sea `mvp/dashboard`. |

## Límites a tener en cuenta

- El plan **Hobby** de Vercel es para uso personal y no comercial. Alcanza para la demo y la defensa del PFI,
  no para un uso institucional con estudiantes reales (ver el Capítulo 7, "Niveles de validación").
- Los despliegues de **Preview** (otras ramas) usan la misma base que producción. No conviene desplegar desde
  otras ramas migraciones que todavía no estén en `main`.
- Una respuesta de la API no puede pasar de 4,5 MB. Ninguna de las respuestas actuales llega a eso con
  evaluaciones de tamaño normal. Una sesión con muchísimos eventos sería el primer lugar donde podría notarse.
