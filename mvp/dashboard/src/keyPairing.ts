// Emparejamiento de pulsaciones en el navegador (Incremento 16).
//
// La duración de cada pulsación (dwell time) se calcula acá, emparejando la liberación con
// la pulsación de la MISMA tecla. El código de la tecla se usa solo en memoria y nunca se
// envía: el evento que sale al servidor es { type: "keyup", dwell } (RNF01). Además:
// - la repetición automática (tecla mantenida) no genera pulsaciones nuevas;
// - al perder el foco o al ocultarse la pestaña se descartan las pulsaciones abiertas, cuya
//   liberación puede no llegar a la página;
// - una liberación sin pulsación registrada se informa con dwell = null.

export type KeyEvent = { type: "keydown" } | { type: "keyup"; dwell: number | null };

export class KeyPairer {
  private pending = new Map<string, number>();

  /** Pulsación. Devuelve el evento a registrar, o null si es repetición automática. */
  down(code: string, t: number, repeat = false): KeyEvent | null {
    if (repeat || this.pending.has(code)) return null;
    this.pending.set(code, t);
    return { type: "keydown" };
  }

  /** Liberación: duración desde la pulsación de la misma tecla. */
  up(code: string, t: number): KeyEvent {
    const start = this.pending.get(code);
    this.pending.delete(code);
    return { type: "keyup", dwell: start === undefined ? null : Math.max(0, t - start) };
  }

  /** Pérdida de foco u ocultamiento: se descartan las pulsaciones abiertas. */
  reset(): void {
    this.pending.clear();
  }

  get openCount(): number {
    return this.pending.size;
  }
}
