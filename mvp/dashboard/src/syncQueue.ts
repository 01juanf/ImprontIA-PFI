// Cola de sincronización de eventos del lado del estudiante (Incremento 10).
//
// Cap. 15, "Captura de señales": "El envío de lotes de eventos contemplará reintentos
// con backoff ante fallas de red y un buffer local acotado en el cliente mientras dure
// la sesión, de modo que una caída transitoria de conectividad no interrumpa la
// evaluación ni descarte evidencia de forma silenciosa. El agotamiento del buffer o una
// falla persistente se registrarán como evento propio, visible para la revisión docente."
//
// Lógica pura (sin DOM ni red) para poder probarla con `node --test`
// (dashboard/tests/syncQueue.test.ts). TakeExam.tsx la usa con el reloj y la API reales.

import type { CapturedEvent } from "./capture";

export interface SyncConfig {
  baseDelayMs: number; // intervalo normal entre envíos
  maxDelayMs: number; // tope del backoff
  maxBufferedEvents: number; // capacidad del buffer local (buffer + lotes pendientes)
  persistentFailureAfter: number; // fallas consecutivas a partir de las cuales se registra la interrupción
}

export const DEFAULT_SYNC_CONFIG: SyncConfig = {
  baseDelayMs: 5_000,
  maxDelayMs: 60_000,
  // ~15 eventos/s con teclado y mouse habilitados → unos 20 minutos sin conexión.
  maxBufferedEvents: 20_000,
  persistentFailureAfter: 3,
};

export interface Batch {
  seq: number; // número de lote: el backend lo usa para descartar reenvíos (idempotencia)
  events: CapturedEvent[];
}

/**
 * Espera antes del próximo intento: el intervalo base sin fallas, y luego
 * base * 2^fallas con un ±20 % de variación aleatoria (para que muchos
 * estudiantes que pierden la conexión a la vez no reintenten sincronizados),
 * con un tope de `maxDelayMs`.
 */
export function backoffDelay(failures: number, cfg: SyncConfig = DEFAULT_SYNC_CONFIG, random: () => number = Math.random): number {
  if (failures <= 0) return cfg.baseDelayMs;
  const exp = cfg.baseDelayMs * 2 ** failures;
  const jitter = 0.8 + 0.4 * random();
  return Math.round(Math.min(cfg.maxDelayMs, exp * jitter));
}

export class SyncQueue {
  readonly cfg: SyncConfig;
  private buffer: CapturedEvent[] = [];
  private pending: Batch[] = [];
  private nextSeq = 1;
  private dropped = 0;
  private droppedFromT: number | null = null;
  private droppedToT: number | null = null;
  private failures = 0;
  private failingSinceT: number | null = null;
  sentEvents = 0;
  /** Lotes que el servidor rechazó por inválidos (422) y se descartaron sin reintentar. */
  rejectedBatches = 0;
  /** Eventos contenidos en esos lotes rechazados. */
  rejectedEvents = 0;

  /**
   * `startSeq`: primer número de lote a usar. Al retomar una sesión después de recargar la
   * página se continúa desde el último usado, porque el backend descarta como reenvío
   * cualquier lote con `seq` menor o igual al último que aplicó.
   */
  constructor(cfg: SyncConfig = DEFAULT_SYNC_CONFIG, startSeq = 1) {
    this.cfg = cfg;
    this.nextSeq = Math.max(1, Math.floor(startSeq));
  }

  /** Número que tomará el próximo lote (se persiste para retomar la sesión). */
  get nextSeqValue(): number {
    return this.nextSeq;
  }

  /** Eventos que ocupan el buffer local (todavía sin confirmar por el servidor). */
  get bufferedCount(): number {
    return this.buffer.length + this.pending.reduce((n, b) => n + b.events.length, 0);
  }

  get pendingBatches(): number {
    return this.pending.length;
  }

  get consecutiveFailures(): number {
    return this.failures;
  }

  get droppedSinceLastReport(): number {
    return this.dropped;
  }

  /**
   * Agrega un evento capturado. Si el buffer está lleno, el evento se descarta pero se
   * cuenta (con el rango temporal) para registrarlo después como `buffer_overflow`:
   * se conserva la evidencia más antigua, que es la que ya está en cola.
   */
  push(evt: CapturedEvent): boolean {
    if (this.bufferedCount >= this.cfg.maxBufferedEvents) {
      this.dropped += 1;
      if (this.droppedFromT === null) this.droppedFromT = evt.t;
      this.droppedToT = evt.t;
      return false;
    }
    this.buffer.push(evt);
    return true;
  }

  /** Cierra el buffer actual en un lote nuevo (si hay eventos). */
  seal(): void {
    if (this.buffer.length === 0) return;
    this.pending.push({ seq: this.nextSeq++, events: this.buffer.splice(0, this.buffer.length) });
  }

  /** Próximo lote a enviar (siempre el más antiguo: el orden se preserva). */
  peek(): Batch | undefined {
    return this.pending[0];
  }

  /** El servidor confirmó el lote más antiguo. `nowT`: ms desde el inicio de la sesión. */
  ack(nowT: number): void {
    const batch = this.pending.shift();
    if (batch) this.sentEvents += batch.events.length;
    this.recovered(nowT);
  }

  /**
   * El servidor rechazó el lote más antiguo por inválido (422): reenviarlo daría siempre el
   * mismo resultado y bloquearía la cola. Se descarta, se cuenta como evidencia perdida y se
   * registra con el mismo evento `buffer_overflow` que el buffer lleno (el backend ya lo admite
   * y lo muestra al docente como captura incompleta); el resto de la cola sigue fluyendo.
   */
  reject(nowT: number): Batch | undefined {
    const batch = this.pending.shift();
    if (!batch) return undefined;
    this.rejectedBatches += 1;
    this.rejectedEvents += batch.events.length;
    // Solo se cuentan los eventos capturados: si el lote rechazado era de estado, no se re-informa.
    const captured = batch.events.filter((e) => e.type !== "buffer_overflow" && e.type !== "sync_failure");
    if (captured.length > 0) {
      this.dropped += captured.length;
      const ts = captured.map((e) => e.t);
      const from = Math.min(...ts);
      const to = Math.max(...ts);
      this.droppedFromT = this.droppedFromT === null ? from : Math.min(this.droppedFromT, from);
      this.droppedToT = this.droppedToT === null ? to : Math.max(this.droppedToT, to);
    }
    this.recovered(nowT); // el servidor respondió: la conexión funciona
    return batch;
  }

  private recovered(nowT: number): void {
    // Recuperación tras una interrupción prolongada: se deja constancia como evento propio.
    if (this.failures >= this.cfg.persistentFailureAfter && this.failingSinceT !== null) {
      this.buffer.push({
        t: this.failingSinceT,
        type: "sync_failure",
        failed_attempts: this.failures,
        duration_ms: Math.max(0, nowT - this.failingSinceT),
      });
    }
    this.failures = 0;
    this.failingSinceT = null;

    // Con lugar otra vez en el buffer, se registra cuántos eventos se perdieron y cuándo.
    if (this.dropped > 0) {
      this.buffer.push({
        t: this.droppedFromT ?? nowT,
        type: "buffer_overflow",
        dropped: this.dropped,
        from_t: this.droppedFromT,
        to_t: this.droppedToT,
      });
      this.dropped = 0;
      this.droppedFromT = null;
      this.droppedToT = null;
    }
  }

  /** Falló el envío del lote más antiguo: queda en cola y crece el backoff. */
  fail(nowT: number): void {
    if (this.failures === 0) this.failingSinceT = nowT;
    this.failures += 1;
  }

  nextDelay(random: () => number = Math.random): number {
    return backoffDelay(this.failures, this.cfg, random);
  }
}

/** Respuestas del servidor que indican un lote inválido: reenviarlo no cambia el resultado. */
export function isRejectedBatchStatus(status: number | undefined): boolean {
  return status === 422;
}
