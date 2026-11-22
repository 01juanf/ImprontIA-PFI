// Incremento 16: emparejamiento de pulsaciones en el navegador.
import { test } from "node:test";
import assert from "node:assert/strict";
import { KeyPairer } from "../src/keyPairing.ts";

test("teclas superpuestas y liberadas en otro orden conservan su duración", () => {
  const k = new KeyPairer();
  assert.deepEqual(k.down("KeyA", 0), { type: "keydown" });
  assert.deepEqual(k.down("KeyB", 30), { type: "keydown" });
  assert.deepEqual(k.up("KeyB", 60), { type: "keyup", dwell: 30 });
  assert.deepEqual(k.up("KeyA", 120), { type: "keyup", dwell: 120 });
});

test("la repetición automática no genera pulsaciones nuevas", () => {
  const k = new KeyPairer();
  k.down("KeyA", 0);
  assert.equal(k.down("KeyA", 500, true), null);
  assert.equal(k.down("KeyA", 530), null); // sin flag repeat pero la tecla sigue abajo
  assert.deepEqual(k.up("KeyA", 900), { type: "keyup", dwell: 900 });
});

test("al perder el foco se descartan las pulsaciones abiertas", () => {
  const k = new KeyPairer();
  k.down("KeyA", 0);
  k.reset();
  assert.equal(k.openCount, 0);
  assert.deepEqual(k.up("KeyA", 5000), { type: "keyup", dwell: null });
});

test("el evento nunca incluye la identidad de la tecla", () => {
  const k = new KeyPairer();
  const down = k.down("KeyZ", 0) as Record<string, unknown>;
  const up = k.up("KeyZ", 80) as Record<string, unknown>;
  for (const e of [down, up]) assert.ok(!("code" in e) && !("key" in e));
});
