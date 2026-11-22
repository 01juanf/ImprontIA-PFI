// Pruebas de los textos del Incremento 16 (estado del modelo, guía del panorama, duraciones).
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  MODEL_FEATURES_NOTE,
  MODEL_STATE_LABELS,
  MODEL_STATE_SHORT,
  PANORAMA_GUIDE,
  PANORAMA_METRIC_LABELS,
  formatPanoramaValue,
} from "../src/format.ts";

const ESTADOS = ["pendiente", "no_evaluada", "sin_marca", "con_marca"]; // backend: Session.estado_modelo

test("estado del modelo: los cuatro estados del backend tienen etiqueta larga y corta", () => {
  assert.deepEqual(Object.keys(MODEL_STATE_LABELS).sort(), [...ESTADOS].sort());
  assert.deepEqual(Object.keys(MODEL_STATE_SHORT).sort(), [...ESTADOS].sort());
  assert.match(MODEL_STATE_LABELS.pendiente, /cerrar la evaluación/);
});

test("panorama: etiquetas para las seis métricas de panorama.py, incluida la duración real", () => {
  assert.deepEqual(Object.keys(PANORAMA_METRIC_LABELS), [
    "session_wall_duration_ms",
    "session_duration_ms",
    "idle_ratio",
    "paste_chars_total",
    "tab_switch_count",
    "focus_loss_duration_total_ms",
  ]);
});

test("las variables del modelo se presentan como descriptivas, no como explicación", () => {
  assert.match(MODEL_FEATURES_NOTE, /no explican/);
  assert.match(PANORAMA_GUIDE.modelo, /no explican/);
  for (const k of ["metricas", "indicadores", "modelo"] as const) assert.ok(PANORAMA_GUIDE[k].startsWith("¿"));
});

test("duraciones: el redondeo nunca muestra 60 s", () => {
  assert.equal(formatPanoramaValue("session_wall_duration_ms", 119_600), "2 min 0 s");
  assert.equal(formatPanoramaValue("session_wall_duration_ms", 90_400), "1 min 30 s");
  assert.equal(formatPanoramaValue("session_duration_ms", 59_400), "59 s");
  assert.equal(formatPanoramaValue("session_duration_ms", 59_700), "1 min 0 s");
  assert.equal(formatPanoramaValue("session_duration_ms", 4_250), "4,3 s");
});
