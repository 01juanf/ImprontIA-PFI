/**
 * Paquete de reproducibilidad: identificador de la versión que se está usando.
 * La versión (archivo VERSION) y el commit (VITE_GIT_COMMIT) se fijan al compilar; el pie del
 * panel y del ingreso los muestran como «ImprontIA v1.0.0 · commit abc1234».
 */
export const UNKNOWN_COMMIT = "desconocido";

/** Primeros 7 caracteres de un hash de git; «desconocido» si no se pasó al compilar. */
export function shortCommit(commit: string | undefined | null): string {
  const c = (commit ?? "").trim();
  if (!c || c === UNKNOWN_COMMIT) return UNKNOWN_COMMIT;
  return /^[0-9a-f]{8,40}$/i.test(c) ? c.slice(0, 7).toLowerCase() : c;
}

export function versionLabel(version: string | undefined | null, commit: string | undefined | null): string {
  const v = (version ?? "").trim() || "desconocida";
  return `ImprontIA v${v} · commit ${shortCommit(commit)}`;
}
