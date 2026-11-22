// Pruebas unitarias de la cola de sincronización (Incremento 10).
// Ejecutar con: npm test  (node --test con eliminación de tipos, sin dependencias extra)
import { test } from "node:test";
import assert from "node:assert/strict";
import { SyncQueue, backoffDelay, isRejectedBatchStatus, DEFAULT_SYNC_CONFIG, type SyncConfig } from "../src/syncQueue.ts";

const cfg: SyncConfig = { baseDelayMs: 5_000, maxDelayMs: 60_000, maxBufferedEvents: 5, persistentFailureAfter: 3 };
const ev = (t: number) => ({ t, type: "keydown" });

test("backoff: intervalo base sin fallas, crece exponencialmente y respeta el tope", () => {
  const mid = () => 0.5; // sin variación aleatoria (jitter = 1)
  assert.equal(backoffDelay(0, cfg, mid), 5_000);
  assert.equal(backoffDelay(1, cfg, mid), 10_000);
  assert.equal(backoffDelay(2, cfg, mid), 20_000);
  assert.equal(backoffDelay(3, cfg, mid), 40_000);
  assert.equal(backoffDelay(4, cfg, mid), 60_000);
  assert.equal(backoffDelay(10, cfg, mid), 60_000);
  // La variación aleatoria queda dentro de ±20 %.
  assert.equal(backoffDelay(1, cfg, () => 0), 8_000);
  assert.equal(backoffDelay(1, cfg, () => 1), 12_000);
});

test("los lotes conservan el orden y el número de secuencia no se reutiliza", () => {
  const q = new SyncQueue(cfg);
  q.push(ev(1));
  q.push(ev(2));
  q.seal();
  q.push(ev(3));
  q.seal();
  assert.deepEqual(q.peek(), { seq: 1, events: [ev(1), ev(2)] });
  q.fail(100); // el lote 1 queda en cola: se reenvía el mismo, con el mismo seq
  assert.equal(q.peek()?.seq, 1);
  q.ack(200);
  assert.equal(q.peek()?.seq, 2);
  q.ack(300);
  assert.equal(q.peek(), undefined);
  assert.equal(q.sentEvents, 3);
});

test("buffer acotado: lo que no entra se cuenta y se registra como buffer_overflow al recuperar", () => {
  const q = new SyncQueue(cfg);
  for (let t = 0; t < 8; t++) q.push(ev(t)); // capacidad 5: se descartan t = 5, 6, 7
  assert.equal(q.bufferedCount, 5);
  assert.equal(q.droppedSinceLastReport, 3);
  q.seal();
  q.ack(1_000);
  q.seal();
  const meta = q.peek()!.events;
  assert.deepEqual(meta, [{ t: 5, type: "buffer_overflow", dropped: 3, from_t: 5, to_t: 7 }]);
  assert.equal(q.droppedSinceLastReport, 0);
});

test("una falla breve no deja rastro; una persistente se registra como sync_failure", () => {
  const q = new SyncQueue(cfg);
  q.push(ev(0));
  q.seal();
  q.fail(1_000);
  q.fail(2_000);
  q.ack(3_000); // 2 fallas < 3: interrupción breve, no se registra
  q.seal();
  assert.equal(q.peek(), undefined);

  q.push(ev(4_000));
  q.seal();
  q.fail(5_000);
  q.fail(15_000);
  q.fail(35_000);
  assert.equal(q.consecutiveFailures, 3);
  assert.equal(q.nextDelay(() => 0.5), 40_000);
  q.ack(75_000);
  q.seal();
  assert.deepEqual(q.peek()!.events, [{ t: 5_000, type: "sync_failure", failed_attempts: 3, duration_ms: 70_000 }]);
  assert.equal(q.consecutiveFailures, 0);
  assert.equal(q.nextDelay(), 5_000);
});

test("los eventos de estado de la captura entran aunque el buffer esté lleno", () => {
  const q = new SyncQueue({ ...cfg, maxBufferedEvents: 2 });
  q.push(ev(0));
  q.push(ev(1));
  q.push(ev(2)); // descartado
  q.seal();
  q.fail(10);
  q.fail(20);
  q.fail(30);
  q.ack(40);
  q.seal();
  const types = q.peek()!.events.map((e) => e.type);
  assert.deepEqual(types, ["sync_failure", "buffer_overflow"]);
});

test("la configuración por defecto coincide con lo documentado", () => {
  assert.deepEqual(DEFAULT_SYNC_CONFIG, { baseDelayMs: 5_000, maxDelayMs: 60_000, maxBufferedEvents: 20_000, persistentFailureAfter: 3 });
});

test("un lote rechazado (422) se descarta, se cuenta como perdido y el resto sigue en orden", () => {
  const q = new SyncQueue(cfg);
  q.push(ev(10));
  q.push(ev(20));
  q.seal(); // lote 1 (será rechazado)
  q.push(ev(30));
  q.seal(); // lote 2
  q.fail(25); // una falla de red previa no debe quedar contando
  const dropped = q.reject(40);
  assert.equal(dropped?.seq, 1);
  assert.equal(q.rejectedBatches, 1);
  assert.equal(q.rejectedEvents, 2);
  assert.equal(q.consecutiveFailures, 0);
  assert.equal(q.peek()?.seq, 2); // no se reintenta el lote 1: la cola avanza
  q.ack(50);
  q.seal();
  // La pérdida queda registrada como buffer_overflow (tipo ya admitido por el backend).
  assert.deepEqual(q.peek()!.events, [{ t: 10, type: "buffer_overflow", dropped: 2, from_t: 10, to_t: 20 }]);
  assert.equal(q.sentEvents, 1);
});

test("si se rechaza un lote solo con eventos de estado, no se vuelve a informar (sin bucle)", () => {
  const q = new SyncQueue(cfg);
  q.push(ev(1));
  q.seal();
  q.reject(5); // genera el buffer_overflow
  q.seal();
  assert.equal(q.peek()!.events[0].type, "buffer_overflow");
  q.reject(6); // el propio aviso es rechazado
  q.seal();
  assert.equal(q.peek(), undefined);
  assert.equal(q.droppedSinceLastReport, 0);
  assert.equal(q.reject(7), undefined); // cola vacía: no hace nada
});

test("solo el 422 cuenta como lote inválido; las fallas de red o del servidor se reintentan", () => {
  assert.equal(isRejectedBatchStatus(422), true);
  for (const s of [undefined, 0, 401, 409, 500, 502, 503]) assert.equal(isRejectedBatchStatus(s), false);
});

test("al retomar una sesión, la numeración de lotes continúa desde la guardada", () => {
  const q = new SyncQueue(cfg, 7);
  assert.equal(q.nextSeqValue, 7);
  q.push(ev(1));
  q.seal();
  assert.equal(q.peek()?.seq, 7);
  assert.equal(q.nextSeqValue, 8);
  assert.equal(new SyncQueue(cfg, 0).nextSeqValue, 1);
});
