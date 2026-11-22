# ImprontIA — Dashboard

React + TypeScript + Vite. Un solo frontend sirve tanto la vista pública del
estudiante (sin login, toma el examen y ahí mismo se capturan las señales)
como el panel del docente (protegido con JWT) — así lo pide cap. 15: la
captura ocurre "en el navegador mediante APIs y eventos nativos de la
plataforma web", como parte del propio frontend. Ver `../docs/bitacora.md`
(Incrementos 2b, 4, 7, 8 y 10) y `../ARCHITECTURE.md` para el razonamiento completo.

Sin librerías de estado/datos adicionales (React Query, Redux, etc.) — el
alcance del MVP no las justifica todavía.

## Setup

```bash
npm install
cp .env.example .env   # opcional: por defecto apunta a http://localhost:8010
npm run dev            # http://localhost:5173 (el backend permite CORS solo desde este origen)
```

Requiere el backend corriendo (ver `../backend/README.md`).

```bash
npm run build          # verificación de tipos (tsc) + bundle de producción en dist/
npm test               # pruebas unitarias de la cola de sincronización (node --test, Node >= 22)
npx oxlint src tests   # lint (sin argumentos, oxlint recorre también node_modules)
```

## Estructura

```
src/
├── api.ts                 Cliente HTTP tipado + tipos que reflejan app/schemas.py del backend
├── capture.ts             Captura de eventos DOM (teclado/mouse/scroll/visibilidad/portapapeles),
│                          filtrada por allowed_signals (RF04) — nunca lee el texto tipeado
├── syncQueue.ts           Buffer local acotado + lotes numerados + backoff exponencial; registra
│                          buffer agotado / falla persistente como eventos propios (Incremento 10)
├── format.ts              Fechas (UTC → hora local, 24 h), etiquetas legibles de indicadores/estados
│                          y la descripción de cada señal que ve el estudiante antes de consentir
├── Layout.tsx             Shell del panel docente + guard de autenticación (RequireAuth) + contador de pendientes
├── App.tsx                Rutas (públicas y protegidas)
├── PolicyCard.tsx         Política de captura vigente y su versionado (editar = versión nueva, RNF04)
├── ReviewStatusBadge.tsx  Estado de revisión docente (sin revisar / revisada / validación pendiente)
└── pages/
    ├── Login.tsx
    ├── ExamsList.tsx          Crear evaluación (info, reglas, consigna, señales), ver join_code
    ├── SessionsList.tsx       Sesiones de una evaluación, filtro "requieren revisión", política
    ├── SessionDetail.tsx      Contexto, indicadores trazables (el del modelo, con su posición
    │                          relativa en la línea base, sin score crudo), métricas, revisión e historial
    ├── PendingValidations.tsx Validaciones adicionales pendientes de todas las evaluaciones (RF11/HU08)
    └── TakeExam.tsx           Vista pública /exam/:joinCode — el estudiante rinde acá:
                               info/reglas + señales registradas → consentimiento → consigna +
                               respuesta, con capture.ts y syncQueue.ts corriendo en la misma página
tests/
└── syncQueue.test.ts      Backoff, orden de lotes, buffer lleno, falla breve vs. persistente
```

La vista del estudiante y el panel docente se ejercitan de punta a punta con
`../scripts/capturas_demo.py`, `../scripts/prueba_interna.py` y
`../scripts/prueba_red.py` (Playwright).
