import { readFileSync } from 'node:fs'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Paquete de reproducibilidad: la versión de la entrega sale del archivo VERSION de mvp/ (o de
// package.json, p. ej. en la imagen Docker, cuyo contexto es solo dashboard/). El commit llega
// como VITE_GIT_COMMIT al compilar (ver src/version.ts y el README, "Reproducibilidad").
function appVersion(): string {
  for (const file of ['../VERSION', './package.json']) {
    try {
      const text = readFileSync(new URL(file, import.meta.url), 'utf-8')
      const v = file.endsWith('.json') ? JSON.parse(text).version : text.split('\n')[0].trim()
      if (v) return v
    } catch {
      // sigue con la próxima fuente
    }
  }
  return 'desconocida'
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  define: {
    __APP_VERSION__: JSON.stringify(process.env.VITE_APP_VERSION || appVersion()),
  },
})
