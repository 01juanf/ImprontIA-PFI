// Kit de simulación (Fase 2, P03): selector de condición solo con ?simulacion=1.
import { test } from "node:test";
import assert from "node:assert/strict";
import { SIMULATION_CONDITIONS, isSimulationMode, simulationConditionToSend } from "../src/format.ts";

test("las condiciones son las mismas que acepta el backend", () => {
  assert.deepEqual(
    SIMULATION_CONDITIONS.map((c) => c.value),
    ["normal", "pegado", "transcripcion", "consulta_externa", "suplantacion"],
  );
});

test("el modo simulación se activa solo con el parámetro del enlace", () => {
  assert.equal(isSimulationMode(""), false);
  assert.equal(isSimulationMode("?otra=1"), false);
  assert.equal(isSimulationMode("?simulacion=0"), false);
  assert.equal(isSimulationMode("?simulacion=1"), true);
  assert.equal(isSimulationMode("?x=2&simulacion=true"), true);
});

test("sin modo simulación nunca se envía una condición", () => {
  assert.equal(simulationConditionToSend(false, "pegado"), undefined);
  assert.equal(simulationConditionToSend(true, "pegado"), "pegado");
  assert.equal(simulationConditionToSend(true, ""), undefined);
  assert.equal(simulationConditionToSend(true, "trampa"), undefined);
});
