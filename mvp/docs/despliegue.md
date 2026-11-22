# Despliegue de ImprontIA (Fase 2, P01)

Objetivo: que Martina y Juan usen el MVP **desde dos computadoras distintas** (docente en una, estudiante en otra) para las simulaciones de examen. Hay dos caminos:

| Camino | Cuándo conviene | HTTPS | Costo |
|---|---|---|---|
| **A. Docker Compose** en una computadora | Las dos personas en la misma red (casa, facultad), o para probar | No (red local) | 0 |
| **B. Render** (en la nube) | Cada uno desde su casa, con una URL pública, datos que persisten | Sí, automático | Planes pagos chicos (ver "Elegir un camino") |

En los dos casos el backend corre en **modo producción** (`IMPRONTIA_ENV=production`): **no arranca sin un `JWT_SECRET` propio** (mínimo 32 caracteres). Con el secreto de desarrollo, cualquiera podría firmar un token de docente.

## Variables de entorno del backend

| Variable | Obligatoria | Qué es |
|---|---|---|
| `IMPRONTIA_ENV` | sí, en producción | `production` activa las validaciones. Sin ella, todo se comporta como en desarrollo. |
| `JWT_SECRET` | **sí** | Secreto de los tokens del docente. Generarlo con `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Si se cambia, los docentes tienen que volver a iniciar sesión (nada más se pierde). |
| `DATABASE_URL` | sí | PostgreSQL. Acepta el formato de los servicios (`postgres://…` o `postgresql://…`, con `?sslmode=require` incluido) y lo pasa solo al driver `psycopg2`. Sin ella usa SQLite local (solo desarrollo). |
| `CORS_ORIGINS` | sí, si el dashboard está en otra URL | URL pública del dashboard (varias, separadas por coma, sin barra final). Default: `http://localhost:5173`. |
| `SEED_TEACHERS` | no | Docentes que se crean al arrancar si no existen: `martina@uade.edu.ar:clave1,juan@uade.edu.ar:clave2`. Útil donde no hay consola. **Nunca** cambia la clave de un docente que ya existe. |
| `DB_POOL_SIZE` / `DB_POOL_MAX` | no | Conexiones a PostgreSQL abiertas en reposo (default 5) y máximo simultáneo (default 40, mínimo 12). Ver "Ajustes opcionales". |
| `PORT` | no | Lo fija el hosting; en local, 8000. |

Del dashboard: **`VITE_API_URL`** (URL pública de la API). Vite la incrusta al **compilar**: si cambia, hay que volver a construir el dashboard.

## A. Docker Compose (una computadora, red local)

Requisitos: Docker Desktop.

```bash
cd mvp
cp .env.example .env
# editar .env: pegar un JWT_SECRET generado; opcional SEED_TEACHERS
docker compose up --build -d
docker compose ps                      # db y backend deben quedar "healthy"
python scripts/verificar_despliegue.py --api http://localhost:8010 \
    --email martina@uade.edu.ar --clave 'clave1' --origen http://localhost:5173
```

- Dashboard: <http://localhost:5173> · API: <http://localhost:8010/health>.
- Docente sin `SEED_TEACHERS`: `docker compose exec backend python -m scripts.seed_teacher mail clave`.
- **Desde otra computadora de la misma red:** en `.env`, `PUBLIC_API_URL=http://<IP-de-esta-máquina>:8010` y `CORS_ORIGINS=http://<IP>:5173`; luego `docker compose up --build -d`. La otra persona entra a `http://<IP>:5173`. Sin HTTPS: sirve para simular, no para datos reales de estudiantes.
- Metabase (opcional, para explorar la base): `docker compose --profile metabase up -d` → <http://localhost:3000>.
- Los datos quedan en el volumen `improntia_db_data`: sobreviven a `docker compose down` (no usar `down -v`).
- Copia de seguridad: `docker compose exec db pg_dump -U improntia improntia > respaldo.sql` (o `scripts/respaldar_base.py`, ver B, paso 6).

## B. En la nube con Render (URL pública con HTTPS, datos que persisten)

Esta guía está pensada para hacerla **sin conocimientos técnicos**, desde el navegador. Al final hay
dos URL: la del **dashboard** (la que se abre para usar ImprontIA) y la de la **API** (la usa el
dashboard por detrás).

### Elegir un camino

**Costos y recomendación** (precios de las páginas oficiales, consultados el 30/10/2026; revisarlos
al crear las cuentas porque cambian):

| Opción | Costo/mes | Datos | ¿Se duerme? | Respaldos |
|---|---|---|---|---|
| **B2 recomendado:** Neon Free (`aws-us-east-1`) + API Render `0.5c-512mb` + dashboard estático | ~USD 7 | Persisten (1 GB) | No | Neon Free guarda poco (6 h + 1 snapshot): hacer `respaldar_base.py` semanal |
| **B1 más robusto:** todo en Render (Postgres `0.1c-256mb` + API `0.5c-512mb`) | ~USD 13 | Persisten (1 GB, ampliable) | No | PITR 3 días + respaldos lógicos 7 días incluidos |
| **Gratis:** Neon Free + API Render `free` (cambiar `plan:` en `render.externo.yaml`) | USD 0 | Persisten | Sí: tras 15 min sin uso, el primer pedido tarda ~1 min | Igual que B2 |

La demo completa (sección «Cargar los datos de demostración») ocupa ~50 MB en escala liviana, así que
1 GB alcanza para la demo más cientos de sesiones reales. Neon avisa que puede borrar proyectos Free
con 90 días sin actividad (aviso publicado para regiones Azure; no está confirmado para AWS): usar la
plataforma o hacer un respaldo al menos una vez por mes lo evita. Render no tiene región en
Sudamérica; desde Argentina la latencia a Virginia es aceptable para este uso.


Hay dos caminos; los dos dejan la plataforma **siempre encendida** y con **datos que no se borran**.
La diferencia es dónde vive la base de datos:

| | **B1. Todo en Render** | **B2. Base en Neon (o Supabase) + Render** |
|---|---|---|
| Archivo que usa Render | `render.yaml` | `render.externo.yaml` |
| Base de datos | Render (plan pago `0.1c-256mb`) | Neon o Supabase (cuenta aparte) |
| API | Render (plan pago `0.5c-512mb`, no se duerme) | Igual |
| Dashboard | Render, sitio estático (sin costo) | Igual |
| Cuentas a crear | 1 (Render) | 2 (Render + Neon) |
| Datos a copiar a mano | ninguno | la URL de la base |

**No usar planes `free` de Render para datos reales:** la base gratuita de Render **vence a los
30 días** (14 días más de gracia y después Render la borra con todos los datos) y la API gratuita se
duerme tras 15 minutos sin uso (tarda ~1 minuto en despertar). Fuente: <https://render.com/docs/free>
(consultada el 30/10/2026). Cómo volver a `free` para una prueba: ver los comentarios al principio de
`render.yaml`.

### Paso 0 — Lo que hace falta antes de empezar

1. El código en GitHub, en la rama **`produccion`**, con `render.yaml` y `render.externo.yaml` en la
   **raíz** del repo. Render despliega lo que haya en esa rama de GitHub, no lo que tengas en tu
   computadora. Si la rama no existe o está vieja, creala/actualizala desde la versión que querés
   publicar (en una terminal, en la carpeta del repo, después de hacer commit de los cambios):
   ```bash
   git checkout -B produccion      # crea la rama (o la mueve) al commit actual
   git push -u origin produccion   # la sube a GitHub
   git checkout -                  # volvés a la rama en la que estabas
   ```
   Para comprobarlo, en GitHub elegí la rama `produccion` y fijate que en la raíz aparezcan
   `render.yaml` y `render.externo.yaml`. Cada vez que quieras publicar cambios, repetí esos tres
   comandos: Render vuelve a desplegar solo.
2. Una **tarjeta** para cargar en Render (los planes pagos la piden).
3. Elegir y anotar en un lugar seguro (un gestor de contraseñas, no un mail):
   - las claves de los docentes, p. ej. una para `martina@uade.edu.ar` y otra para `juan@uade.edu.ar`
     (largas: 12 caracteres o más);
   - si vas a cargar los datos de demostración (sección «Cargar los datos de demostración…»), una
     clave para la cuenta de la demo, `docente@uade.edu.ar`. Conviene que la demo viva en su propia
     cuenta, separada de las cuentas con exámenes reales.

### Paso 1 (solo camino B2) — Crear la base en Neon

1. Entrar a <https://neon.com> → **Sign up** (se puede con la cuenta de GitHub o Google).
2. **Create project**:
   - *Project name*: `improntia`.
   - *Postgres version*: **16** (es la versión con la que se probó todo, y la que permite hacer
     respaldos con `pg_dump` 16; ver "Respaldos").
   - *Region*: **AWS US East (N. Virginia)** (`aws-us-east-1`). Tiene que estar cerca de la API, que
     va en Virginia; no elegir São Paulo si la API está en Render.
3. En el proyecto, botón **Connect**. Aparece la *connection string*, algo así como
   `postgresql://neondb_owner:XXXX@ep-algo-123456.us-east-1.aws.neon.tech/neondb?sslmode=require`.
   - Desactivar la opción **Connection pooling** para copiar la conexión **directa** (el host *no*
     dice `-pooler`). Es la que se probó; también sirve para los respaldos (Neon recomienda la
     conexión directa para `pg_dump`). El backend ya mantiene pocas conexiones abiertas (ver
     `DB_POOL_SIZE`), así que no necesita el pooler.
   - Copiarla **completa**, incluido `?sslmode=require` del final (y `&channel_binding=require` si
     aparece). Es una contraseña: no compartirla.

*Con Supabase en vez de Neon:* Project Settings → Database → *Connection string* → **Session
pooler** (puerto 5432). La conexión "Direct" de Supabase es solo IPv6 y Render no la alcanza. Agregar
`?sslmode=require` al final si no lo trae. El *session pooler* del plan gratuito admite pocas
conexiones (unas 15), así que en la API agregá también la variable `DB_POOL_MAX` = `12` (ver «Ajustes
opcionales del backend»). (Supabase no se probó; ver "Qué se verificó".)

### Paso 2 — Crear la cuenta de Render y conectar GitHub

1. Entrar a <https://dashboard.render.com> → **Sign up** con la cuenta de **GitHub** (así ya queda
   conectada; si pide permisos, dar acceso al repositorio del MVP).
2. Menú de la cuenta → **Billing** → cargar la tarjeta.

### Paso 3 — Crear todo con el Blueprint

1. Botón **New** (arriba) → **Blueprint**.
2. Elegir el repositorio → **Connect**.
3. Completar:
   - *Blueprint Name*: `improntia`.
   - *Branch*: **`produccion`**.
   - *Blueprint Path*: dejar vacío (usa `render.yaml`) para **B1**; escribir **`render.externo.yaml`**
     para **B2**.
4. Render muestra lo que va a crear: en B1 `improntia-db`, `improntia-api` e `improntia-dashboard`;
   en B2 solo `improntia-api` e `improntia-dashboard`. Y pide completar estas variables:

   | Servicio | Variable | Qué poner |
   |---|---|---|
   | `improntia-api` | `CORS_ORIGINS` | `https://improntia-dashboard.onrender.com` |
   | `improntia-api` | `SEED_TEACHERS` | `martina@uade.edu.ar:CLAVE1,juan@uade.edu.ar:CLAVE2` (las claves del paso 0, sin espacios). Si vas a cargar la demo, agregá al final `,docente@uade.edu.ar:CLAVE3` |
   | `improntia-api` | `DATABASE_URL` (**solo B2**) | la URL de Neon del paso 1, completa |
   | `improntia-dashboard` | `VITE_API_URL` | `https://improntia-api.onrender.com` |

   `JWT_SECRET` no se completa: Render lo genera solo. En B1, `DATABASE_URL` tampoco: Render la
   conecta sola con su base.
5. **Deploy Blueprint**. La primera vez tarda unos minutos (la API se construye con Docker).

### Paso 4 — Corregir las URL si Render les puso otro nombre

Si el nombre `improntia-api` o `improntia-dashboard` ya estaba tomado, Render agrega letras
(p. ej. `improntia-api-x7k2.onrender.com`). La URL real se ve arriba de todo en la página de cada
servicio. Si alguna no coincide con lo que se puso en el paso 3:

1. `improntia-api` → **Environment** → corregir `CORS_ORIGINS` con la URL real del dashboard →
   guardar y, si no se vuelve a desplegar solo, **Manual Deploy → Deploy latest commit**.
2. `improntia-dashboard` → **Environment** → corregir `VITE_API_URL` con la URL real de la API →
   guardar y **Manual Deploy → Deploy latest commit** (el dashboard se tiene que volver a compilar:
   la URL de la API queda grabada al compilar).

Sin barra `/` al final en ninguna de las dos.

### Paso 5 — Verificar que funciona

1. Abrir en el navegador `https://<url-de-la-api>/health`. Tiene que mostrar `{"status":"ok", …}`.
2. Abrir `https://<url-del-dashboard>` e iniciar sesión con un docente de `SEED_TEACHERS`.
   Crear una evaluación de prueba y entrar como estudiante desde otra computadora o el celular.
3. (Opcional, con Python instalado) la verificación completa, que recorre todo el flujo:
   ```bash
   python mvp/scripts/verificar_despliegue.py --api https://<url-de-la-api> \
       --email martina@uade.edu.ar --clave '<clave>' --origen https://<url-del-dashboard>
   ```
   Tiene que terminar en `14/14 chequeos OK — DESPLIEGUE VERIFICADO`. Deja una evaluación
   "Verificación de despliegue …" que se puede borrar desde el dashboard.
4. Ya creados los docentes, se puede borrar `SEED_TEACHERS` en *Environment* de la API (no hace
   falta: nunca cambia la clave de un docente que ya existe). Para **agregar** un docente más tarde
   (por ejemplo, la cuenta de la demo): Render → `improntia-api` → *Environment* → editar
   `SEED_TEACHERS` agregando `,email:clave` → *Save Changes*. La API se reinicia y lo crea; Render
   solo pide las variables `sync: false` al crear el Blueprint, después se cambian ahí.

Si algo falla, mirar **Logs** del servicio en Render. Mensajes típicos:
`JWT_SECRET es obligatorio` (falta la variable), `password authentication failed` o
`could not translate host name` (la `DATABASE_URL` está mal copiada), `CORS` en la consola del
navegador (`CORS_ORIGINS` no coincide exactamente con la URL del dashboard).

### Paso 6 — Respaldos (hacerlo siempre antes y después de cada tanda de exámenes)

Los datos persisten en la base, pero conviene tener una copia propia por si se borra algo por error
o se cambia de proveedor. Además de lo que ofrezca cada proveedor (en B1, los respaldos de Render de
la página de la base; en Neon, los *snapshots* y la restauración a un momento anterior de la
consola), el repo trae dos scripts que guardan y recuperan **toda** la base en un archivo:

1. Conseguir la URL **externa** de la base:
   - B1 (Render): página de `improntia-db` → menú **Connect** (arriba a la derecha) o página
     **Info** → *External Database URL*. Agregarle `?sslmode=require` al final. (La que usa la API
     es la *Internal*, que solo funciona dentro de Render.)
   - B2 (Neon): la misma URL del paso 1 (conexión directa).
2. Tener instalado el cliente de PostgreSQL **versión 16** (la de la base):
   macOS `brew install libpq` (y agregar `$(brew --prefix libpq)/bin` al `PATH`);
   Windows: instalador de PostgreSQL 16 de EDB marcando solo *Command Line Tools*;
   Ubuntu: `sudo apt install postgresql-client-16`.
3. Desde la carpeta `mvp/` del repo:
   ```bash
   export DATABASE_URL='<URL externa de la base>'        # en Windows PowerShell: $env:DATABASE_URL='...'
   python scripts/respaldar_base.py
   ```
   Crea `mvp/respaldos/improntia_AAAA-MM-DD_HHMM.dump` y termina en `RESPALDO OK — … (11 tablas: …)`.
   El script **no muestra la clave** de la base. El archivo tiene datos de estudiantes: guardarlo en
   un lugar privado (la carpeta `respaldos/` está en `.gitignore`, no se sube al repo).
4. Para **restaurar** (recuperar datos o mudarse a otra base), con `DATABASE_URL` de la base destino:
   ```bash
   python scripts/restaurar_base.py respaldos/improntia_AAAA-MM-DD_HHMM.dump --confirmar <nombre-de-la-base>
   ```
   `<nombre-de-la-base>` es lo que va después de la última `/` de la URL (p. ej. `neondb` o
   `improntia`): evita restaurar sobre la base equivocada. Reemplaza las tablas de ImprontIA en una
   sola transacción (si falla, la base queda como estaba). Conviene suspender la API mientras tanto
   (Render: *Suspend* / *Resume*).

**Mudarse desde una base free de Render ya creada** (antes de que venza): respaldar con su
*External Database URL*, restaurar en la base nueva, poner la URL nueva en `DATABASE_URL` de
`improntia-api` (*Environment*) y recién después borrar la base vieja.

### Ajustes opcionales del backend

- `DB_POOL_SIZE` (default 5) y `DB_POOL_MAX` (default 40, mínimo 12): conexiones a la base que la
  API deja abiertas en reposo y máximo simultáneo. Los defaults entran en los planes chicos; bajar
  `DB_POOL_MAX` solo si el proveedor avisa que se superó su límite de conexiones.
- La región (`virginia`) y la versión de PostgreSQL (16) **no se pueden cambiar** después de crear
  los servicios. Si ya existía un Blueprint creado con el `render.yaml` anterior (región por
  defecto, Oregon), Render no va a poder sincronizar la región: borrar las líneas `region:` o crear
  el Blueprint de nuevo.

**Railway** sirve igual (mismas variables, mismo Dockerfile, `rootDir` = `mvp/backend`; el dashboard
con `npm install && npm run build` y `VITE_API_URL`), pero no tiene Blueprint compatible con estos
archivos.

## Cargar los datos de demostración en la plataforma desplegada

> **Atención: son datos SINTÉTICOS.** Las 149 entregas, los códigos de participante
> (P-101, P-102, …), las respuestas y las revisiones son inventados por un programa. No
> corresponden a ninguna persona ni a ningún examen real, y no sirven como resultados de la
> tesis. Solo existen para mostrar cómo se ve la plataforma "con uso" en la presentación.

### Qué queda cargado

En la cuenta `docente@uade.edu.ar` quedan seis evaluaciones con fechas del cuatrimestre: los
parciales 1 de hace 45 días, cerrados y revisados; el TP a libro abierto de hace 24 días; los
parciales 2 de hace 3 días, uno revisado a medias (con una validación pendiente) y otro sin
revisar; y el **Recuperatorio abierto con 19 entregas**. En vivo se rinde una entrega más, se
llega a 20 y "Cerrar y analizar" ya ejecuta el modelo.

Las evaluaciones de otros docentes no se tocan. Si la cuenta de la demo tiene una evaluación
que no es de la demo, el script se detiene sin borrar ni cargar nada.

### Antes de empezar (una sola vez)

1. **La cuenta del docente tiene que existir en la plataforma.** El script no la crea. En el
   servicio de la API (Render → servicio de la API → *Environment*), la variable
   `SEED_TEACHERS` tiene que incluir `docente@uade.edu.ar:<clave>`. Para comprobarlo, entrá al
   dashboard con ese email y esa clave.
2. **Buscá la URL externa de la base.** El script la usa para poner cada evaluación en su
   fecha.
   - **Render:** Dashboard → la base PostgreSQL → *Connect* (o *Info → Connections*) →
     **External Database URL**. Copiá la *externa*: la *interna* solo funciona dentro de Render.
   - **Neon:** el proyecto → *Connect* → la *connection string*. Ya trae `?sslmode=require`.
   - **Supabase:** *Project Settings → Database → Connection string → URI*. Usá la del
     *Session pooler*, y cambiá `[YOUR-PASSWORD]` por la clave de la base.
   - Esa URL contiene la clave de la base. No la pegues en documentos ni en chats.
3. Tené el repositorio en tu computadora, con el entorno del backend instalado
   (`mvp/backend/.venv`, como para correr los tests).

### El comando

Desde la carpeta `mvp/backend` (en Windows, `.venv\Scripts\activate` en lugar de `source`):

```bash
source .venv/bin/activate
python -m scripts.seed_presentacion \
  --api https://LA-URL-DE-TU-API.onrender.com \
  --database-url "LA-URL-EXTERNA-DE-LA-BASE"
```

- El script te pide la clave de `docente@uade.edu.ar` por teclado (no se ve mientras la escribís).
  No la pongas en el comando con `--clave`: quedaría guardada en el historial de la terminal.
- Usá siempre `--api`. Sin `--api`, el script trabaja directo sobre la base (modo local) y, si
  tenés `DATABASE_URL` exportada para los respaldos, lo haría sobre la de producción.
- Si la API estaba "dormida" (en el plan gratuito se apaga a los 15 minutos sin uso), el script
  muestra "Esperando que la API despierte…" y espera hasta 4 minutos. Es normal.
- Si se corta la conexión o la API responde con un error pasajero, el script reintenta solo.
- Corrélo **el mismo día de la presentación**. Las fechas ("hace 3 días", "hoy") se calculan
  desde el momento en que se corre.
- Al final muestra el **código del Recuperatorio** para rendir en vivo.

**Si no tenés la URL de la base:** podés omitir `--database-url` y la carga funciona igual. La
desventaja es que las seis evaluaciones quedan con la fecha de hoy y la duración de cada
entrega se ve en segundos. El script lo avisa al terminar. Para la presentación conviene
usar la URL.

### Cuánto tarda y cuánto ocupa

| | Escala liviana (la que se usa por defecto) | Escala completa (`--escala completa`) |
|---|---|---|
| Eventos cargados | ~177.000 (~1.200 por entrega) | ~690.000 (~4.600 por entrega) |
| Espacio en la base | **~42 MB** (la base queda en ~50 MB) | ~150 MB (la base queda en ~160 MB) |
| Tiempo medido en una computadora (API y base locales) | ~40 segundos | ~2 min 30 s |
| Tiempo estimado contra la nube | **entre 3 y 10 minutos** (no medido) | 4 veces más; no se recomienda en planes gratuitos |

La escala liviana guarda menos pulsaciones de teclado por entrega. Lo que se ve en la
plataforma es lo mismo: las duraciones de los exámenes (de 12 a 17 minutos), las entregas
señaladas y los motivos. Lo único distinto es la cantidad de teclas que figura en el detalle
de cada entrega. Entra cómodo en los planes chicos (Neon Free y Render `0.1c-256mb` traen 1 GB).

### Volver a cargarla (por ejemplo, el día de la presentación)

Agregá `--reiniciar --si-borrar docente@uade.edu.ar` al mismo comando. El script borra **solo**
las seis evaluaciones de la demo de esa cuenta y vuelve a cargarlas con fechas nuevas. Sin
`--si-borrar` y el email exacto, no borra nada. Si lo corrés en una terminal, te pide que
escribas el email.

### Borrar los datos de demostración después

```bash
python -m scripts.seed_presentacion --api https://LA-URL-DE-TU-API.onrender.com \
  --database-url "LA-URL-EXTERNA-DE-LA-BASE" --solo-borrar --si-borrar docente@uade.edu.ar
```

El comando elimina las seis evaluaciones de la demo con todas sus entregas, eventos y
revisiones. No se puede deshacer. Las demás evaluaciones de esa cuenta y las de otros
docentes no se tocan. También se puede borrar cada evaluación desde el dashboard (botón
«Eliminar esta evaluación…» en la página de la evaluación), una por una. No uses "Eliminar mi cuenta": borra la
cuenta entera con todo lo que tiene.

PostgreSQL no le devuelve al proveedor el espacio de lo borrado, pero lo reutiliza. El panel
puede seguir mostrando ~50 MB usados, y una carga nueva ocupa ese mismo lugar, sin sumar.
Para achicar la base de verdad, alguien técnico puede correr `VACUUM FULL events;` en la
consola SQL del proveedor.

### Si algo falla

| Mensaje | Qué hacer |
|---|---|
| "No se pudo ingresar como docente@uade.edu.ar…" | El email o la clave no coinciden con los de `SEED_TEACHERS`. Probá entrar al dashboard con esos datos. |
| "No se pudo conectar a la base…" | Usaste la URL interna o la clave de la base es incorrecta. Copiá de nuevo la URL externa. |
| "…no tiene al docente…" / "…no es la base de la API" | La URL de la base corresponde a otro servicio u otro proyecto. |
| "…ya tiene 6 evaluaciones de la demo" | Ya está cargada. Para recargarla, ver *Volver a cargarla*. |
| "…tiene evaluaciones que NO son de la demo" | Hay datos que no son de la demo en esa cuenta. Conviene usar una cuenta solo para la demo. Si igual querés cargarla sin tocarlos, agregá `--conservar-otras`. |
| "La API no respondió en 240 s" | El servicio está suspendido o la URL está mal. Revisalo en el panel de Render. |

## Qué se verificó y qué no (30/10/2026)

En el entorno de trabajo (sin cuenta de Render ni de Neon), con PostgreSQL 16.15 local **con SSL
activado** (certificado autofirmado) y autenticación por contraseña:

- **Suite del backend:** 135 tests pasan sobre PostgreSQL con `TEST_DATABASE_URL=postgresql://…?sslmode=require`
  (conexión cifrada, como Neon/Supabase) y otra vez con `postgres://…` sin parámetros; sobre SQLite,
  134 pasan y 1 se saltea (el que conecta a PostgreSQL con el formato de los proveedores). Antes de
  estos cambios eran 120.
- **Backend en modo producción** con el comando exacto del contenedor (`uvicorn app.main:app --host
  0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips='*' --timeout-keep-alive 15`, `PORT=8110`),
  `IMPRONTIA_ENV=production`, `JWT_SECRET` de 48 caracteres, `DATABASE_URL=postgres://…?sslmode=require`,
  `SEED_TEACHERS` con dos docentes y `CORS_ORIGINS=https://improntia-dashboard.onrender.com`:
  `verificar_despliegue.py` **14/14 para cada docente**. La base quedó en la migración
  `0004_cierre_y_entrega` y la conexión de la API figuraba cifrada (`pg_stat_ssl`).
- **Conexiones cortadas por el proveedor:** con la API andando se cerraron desde el servidor todas sus
  conexiones (`pg_terminate_backend`); el pedido siguiente respondió 200 (`pool_pre_ping`).
- **Persistencia:** API detenida y vuelta a levantar con **otro** `JWT_SECRET` y `sslmode=prefer`:
  seguían los 2 docentes, 2 evaluaciones, 2 sesiones y 162 eventos; cada docente volvió a entrar
  con su clave y ve su evaluación; el seed no duplicó docentes; un tercer `verificar_despliegue.py`
  dio 14/14.
- **Respaldo y restauración:** `respaldar_base.py` generó un `.dump` de 27 KB con las 11 tablas, sin
  mostrar la clave (tampoco en el error de una clave incorrecta). `restaurar_base.py` lo cargó en otra
  base (dos veces seguidas, la segunda sobre tablas existentes): mismos conteos (2/2/2/162) y misma
  revisión de Alembic. Con `--confirmar` equivocado no toca nada.
- **Dashboard:** `npm install && npm run build` con `VITE_API_URL=http://localhost:8110` genera
  `dist/` (index.html + JS de 332 KB con la URL incrustada).
- **Blueprints:** los dos YAML parsean; campos y nombres de plan (`0.5c-512mb`, `0.1c-256mb`, `free`),
  `region`, `diskSizeGB`, `postgresMajorVersion`, `fromDatabase.connectionString`, `sync: false`,
  "Blueprint Path" y que `dockerfilePath`/`staticPublishPath` son relativos a `rootDir` se
  contrastaron con la documentación de Render del 30/10/2026
  (<https://render.com/docs/blueprint-spec>, <https://render.com/docs/monorepo-support>,
  <https://render.com/docs/infrastructure-as-code>).

**No verificado:** crear los servicios en Render ni la base en Neon/Supabase (requieren las cuentas
de Martina): que Render acepte los Blueprints sin observaciones se ve recién en el paso 3. Tampoco
la conexión a través del pooler de Neon (PgBouncer) ni el *session pooler* de Supabase, la memoria
de 512 MB de la API con muchas sesiones (scikit-learn), ni los contenedores (en el entorno no hay
Docker en funcionamiento). Los nombres de los botones del panel de Render y Neon salen de su
documentación y pueden cambiar.

Verificación anterior (15/10/2026, plan free): 75 tests sobre PostgreSQL 16, `verificar_despliegue.py`
14/14 por docente y persistencia tras reinicio; `docker compose config` válido.

## Seguridad mínima para las simulaciones

- No subir `.env` al repo (está en `.gitignore`). No compartir `JWT_SECRET`.
- Claves de docente largas; cambiar con `scripts.seed_teacher` (Compose) o creando un docente nuevo.
- Las simulaciones son con Martina y Juan como participantes: usar códigos seudónimos, nunca nombres ni legajos.
