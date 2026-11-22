// Captura de señales de interacción DENTRO de la propia plataforma (cap. 15:
// "la captura se realizará en el navegador mediante APIs y eventos nativos
// de la plataforma web"). Reemplaza el enfoque de extensión de Chrome del
// primer intento (ver mvp/docs/bitacora.md) — misma lógica de content.js,
// ahora viviendo en la página del propio examen en vez de inyectada.
//
// Nunca se captura el texto escrito ni el contenido del portapapeles: solo
// metadatos de tiempo (RNF01).

import { KeyPairer } from "./keyPairing";

export interface CapturedEvent {
  t: number; // ms relativos al inicio de la sesión
  type: string;
  [key: string]: unknown;
}

const EVENT_CATEGORY: Record<string, string> = {
  keydown: "keyboard",
  keyup: "keyboard",
  mousemove: "mouse",
  mousedown: "mouse",
  mouseup: "mouse",
  click: "mouse",
  scroll: "scroll",
  visibility: "visibility",
  window_blur: "visibility",
  window_focus: "visibility",
  paste: "clipboard",
  copy: "clipboard",
  cut: "clipboard",
};

function isAllowed(type: string, allowedSignals: string[]): boolean {
  // Minimización (RNF01): una política sin señales habilitadas significa "no capturar nada",
  // no "capturar todo" (antes del Incremento 9 una lista vacía habilitaba todas las señales).
  if (!allowedSignals || allowedSignals.length === 0) return false;
  return allowedSignals.includes(EVENT_CATEGORY[type]);
}

const THROTTLE_MS = 100;

/**
 * Engancha los listeners nativos del DOM y llama a onEvent por cada evento
 * de una categoría habilitada (RF04). Devuelve una función de limpieza.
 */
export function attachCapture(
  startedAt: number,
  allowedSignals: string[],
  onEvent: (e: CapturedEvent) => void
): () => void {
  let lastMouseMove = 0;
  let lastScroll = 0;

  // Nov. 2026: con varios ejercicios, cada evento lleva el ejercicio en el que ocurrió
  // (`item_ref`, el atributo data-item-ref del campo de respuesta). El backend ya calcula las
  // métricas por ítem cuando los eventos lo traen. Para el mouse cuenta dónde está el puntero;
  // para el resto, el campo que tiene el foco.
  function itemRefOf(target?: EventTarget | null): string | undefined {
    const el = target instanceof Element ? target : document.activeElement;
    const ref = el?.closest?.("[data-item-ref]")?.getAttribute("data-item-ref");
    return ref ? ref.slice(0, 64) : undefined;
  }

  function record(evt: { type: string; [k: string]: unknown }, target?: EventTarget | null) {
    if (!isAllowed(evt.type, allowedSignals)) return;
    const item_ref = itemRefOf(target);
    onEvent({ t: Date.now() - startedAt, ...evt, ...(item_ref ? { item_ref } : {}) });
  }

  // NO se envía qué tecla fue (ni `key` ni `code`): la secuencia de teclas físicas permitiría
  // reconstruir lo tecleado (RNF01). Desde el Incremento 16 la duración de cada pulsación se
  // calcula acá, emparejando por tecla solo en memoria (keyPairing.ts), y viaja como `dwell`.
  const keys = new KeyPairer();
  const onKeydown = (e: KeyboardEvent) => {
    const evt = keys.down(e.code, Date.now() - startedAt, e.repeat);
    if (evt) record(evt);
  };
  const onKeyup = (e: KeyboardEvent) => record(keys.up(e.code, Date.now() - startedAt));
  const onMousemove = (e: MouseEvent) => {
    const now = Date.now();
    if (now - lastMouseMove < THROTTLE_MS) return;
    lastMouseMove = now;
    record({ type: "mousemove", x: e.clientX, y: e.clientY }, e.target);
  };
  const onMousedown = (e: MouseEvent) => record({ type: "mousedown", button: e.button, x: e.clientX, y: e.clientY }, e.target);
  const onMouseup = (e: MouseEvent) => record({ type: "mouseup", button: e.button, x: e.clientX, y: e.clientY }, e.target);
  const onClick = (e: MouseEvent) => record({ type: "click", x: e.clientX, y: e.clientY }, e.target);
  const onScroll = () => {
    const now = Date.now();
    if (now - lastScroll < THROTTLE_MS) return;
    lastScroll = now;
    record({ type: "scroll", scrollY: Math.round(window.scrollY), scrollX: Math.round(window.scrollX) });
  };
  const onVisibility = () => {
    if (document.visibilityState === "hidden") keys.reset();
    record({ type: "visibility", state: document.visibilityState });
  };
  const onBlur = () => {
    keys.reset();
    record({ type: "window_blur" });
  };
  const onFocus = () => record({ type: "window_focus" });
  // La API del navegador no ofrece la longitud del contenido pegado sin leerlo: el texto se lee
  // un instante en memoria SOLO para contar caracteres y se descarta (no se guarda ni se envía).
  // Si la categoría "clipboard" no está habilitada, ni siquiera se lee. Desde el Incremento 10
  // esto se le informa al estudiante con estas mismas palabras antes de consentir
  // (format.ts: SIGNAL_STUDENT_DESCRIPTIONS).
  const onPaste = (e: ClipboardEvent) => {
    if (!isAllowed("paste", allowedSignals)) return;
    record({ type: "paste", chars: (e.clipboardData?.getData("text") || "").length });
  };
  const onCopy = () => record({ type: "copy" });
  const onCut = () => record({ type: "cut" });

  document.addEventListener("keydown", onKeydown);
  document.addEventListener("keyup", onKeyup);
  document.addEventListener("mousemove", onMousemove);
  document.addEventListener("mousedown", onMousedown);
  document.addEventListener("mouseup", onMouseup);
  document.addEventListener("click", onClick);
  document.addEventListener("scroll", onScroll, { passive: true });
  document.addEventListener("visibilitychange", onVisibility);
  window.addEventListener("blur", onBlur);
  window.addEventListener("focus", onFocus);
  document.addEventListener("paste", onPaste);
  document.addEventListener("copy", onCopy);
  document.addEventListener("cut", onCut);

  return () => {
    document.removeEventListener("keydown", onKeydown);
    document.removeEventListener("keyup", onKeyup);
    document.removeEventListener("mousemove", onMousemove);
    document.removeEventListener("mousedown", onMousedown);
    document.removeEventListener("mouseup", onMouseup);
    document.removeEventListener("click", onClick);
    document.removeEventListener("scroll", onScroll);
    document.removeEventListener("visibilitychange", onVisibility);
    window.removeEventListener("blur", onBlur);
    window.removeEventListener("focus", onFocus);
    document.removeEventListener("paste", onPaste);
    document.removeEventListener("copy", onCopy);
    document.removeEventListener("cut", onCut);
  };
}
