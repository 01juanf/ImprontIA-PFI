// Pruebas de los textos y formatos del Incremento 12 (panorama, reglas y reencuadre del modelo).
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  INDICATOR_LABELS,
  MODEL_INDICATOR_NOTE,
  RULE_OPTIONS,
  barWidth,
  formatPanoramaValue,
  formatPercent,
} from "../src/format.ts";

test("reencuadre: el indicador del modelo se lee como proceso distinto, con la aclaración", () => {
  assert.equal(INDICATOR_LABELS.atipico_modelo_poblacional, "Proceso de interacción distinto al de la cohorte");
  assert.equal(MODEL_INDICATOR_NOTE, "Indica dónde mirar, no una conducta indebida.");
});

test("reglas: las dos opciones coinciden con los campos de la API", () => {
  assert.deepEqual(RULE_OPTIONS.map((o) => o.value), ["permite_pegado", "permite_otras_pestanas"]);
});

test("panorama: valores legibles por tipo de métrica", () => {
  assert.equal(formatPanoramaValue("session_duration_ms", 4_500), "4,5 s");
  assert.equal(formatPanoramaValue("session_duration_ms", 754_000), "12 min 34 s");
  assert.equal(formatPanoramaValue("idle_ratio", 0.234), "23 %");
  assert.equal(formatPanoramaValue("tab_switch_count", 3), "3");
  assert.equal(formatPanoramaValue("paste_chars_total", 12.25), "12,3");
  assert.equal(formatPanoramaValue("paste_chars_total", null), "—");
  assert.equal(formatPercent(0.5), "50 %");
});

test("panorama: ancho de barra relativo al máximo y acotado", () => {
  assert.equal(barWidth(5, 10), "50.0%");
  assert.equal(barWidth(10, 10), "100.0%");
  assert.equal(barWidth(0, 10), "0%");
  assert.equal(barWidth(3, 0), "0%");
});
