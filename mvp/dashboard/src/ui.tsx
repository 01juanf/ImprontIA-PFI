// Piezas visuales compartidas del rediseño (nov. 2026): marca, chips de estado, huella de
// señales, diálogos de confirmación y estados de carga. Íconos: un solo set (Lucide), el mismo
// del que sale la huella del logo.
import { useEffect, useRef, type ReactNode } from "react";
import { Link } from "react-router-dom";
import {
  AppWindow,
  ClipboardPaste,
  EyeOff,
  Fingerprint,
  Keyboard,
  Loader2,
  MousePointer2,
  MoveVertical,
  WifiOff,
  type LucideIcon,
} from "lucide-react";
import type { ReviewStatus, SessionSummary } from "./api";
import { REVIEW_STATUS_LABELS, indicatorLabel } from "./format";

/* ---------- marca ---------- */

/** Los trazos de la huella del logo (Lucide «fingerprint», recoloreado por la marca). */
const MARK_PATHS: { d: string; accent?: boolean }[] = [
  { d: "M2 12a10 10 0 0 1 18-6", accent: true },
  { d: "M2 16h.01", accent: true },
  { d: "M12 10a2 2 0 0 0-2 2c0 1.02-.1 2.51-.26 4" },
  { d: "M14 13.12c0 2.38 0 6.38-1 8.88" },
  { d: "M17.29 21.02c.12-.6.43-2.3.5-3.02" },
  { d: "M21.8 16c.2-2 .131-5.354 0-6" },
  { d: "M5 19.5C5.5 18 6 15 6 12a6 6 0 0 1 .34-2" },
  { d: "M8.65 22c.21-.66.45-1.32.57-2" },
  { d: "M9 6.8a6 6 0 0 1 9 5.2v2" },
];

export function BrandMark({
  size = 24,
  draw = false,
  stroke = 1.7,
  className = "",
}: {
  size?: number;
  draw?: boolean;
  stroke?: number;
  className?: string;
}) {
  return (
    <svg
      className={`brand-mark${draw ? " brand-draw" : ""} ${className}`}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={stroke}
      aria-hidden="true"
    >
      {MARK_PATHS.map((p) => (
        <path key={p.d} d={p.d} stroke={p.accent ? "var(--brand)" : "currentColor"} />
      ))}
    </svg>
  );
}

export function Wordmark({ to, size = 22 }: { to?: string; size?: number }) {
  const inner = (
    <>
      <BrandMark size={size} />
      <span className="wm-text">
        impront<b>IA</b>
      </span>
    </>
  );
  return to ? (
    <Link to={to} className="wordmark" aria-label="ImprontIA, inicio">
      {inner}
    </Link>
  ) : (
    <span className="wordmark">{inner}</span>
  );
}

/* ---------- señales e indicadores ---------- */

export const SIGNAL_ICONS: Record<string, LucideIcon> = {
  keyboard: Keyboard,
  mouse: MousePointer2,
  scroll: MoveVertical,
  visibility: AppWindow,
  clipboard: ClipboardPaste,
};

/** Nombre corto de cada categoría de señal (para tarjetas y la vista previa). */
export const SIGNAL_SHORT: Record<string, string> = {
  keyboard: "Teclado",
  mouse: "Mouse",
  scroll: "Scroll",
  visibility: "Pestaña y foco",
  clipboard: "Portapapeles",
};

export const INDICATOR_ICONS: Record<string, LucideIcon> = {
  paste_volume_alto: ClipboardPaste,
  cambios_pestana_frecuentes: AppWindow,
  perdida_foco_prolongada: EyeOff,
  ritmo_tecleo_atipico: Keyboard,
  atipico_modelo_poblacional: Fingerprint,
  captura_incompleta: WifiOff,
};

export function indicatorIcon(kind: string): LucideIcon {
  return INDICATOR_ICONS[kind] ?? Fingerprint;
}

/** Orden fijo de la huella: cada casillero es un tipo de indicador. */
const TRACE_SLOTS = [
  "paste_volume_alto",
  "cambios_pestana_frecuentes",
  "perdida_foco_prolongada",
  "ritmo_tecleo_atipico",
  "atipico_modelo_poblacional",
] as const;

/**
 * Huella de una sesión: cinco casilleros, uno por tipo de indicador. Naranja: el indicador
 * prioriza la sesión; azul: está pero no prioriza (permitido por las reglas); negro: la marca
 * del modelo poblacional; vacío: no se generó.
 */
export function Trace({ session }: { session: Pick<SessionSummary, "indicadores" | "estado_modelo"> }) {
  const byKind = new Map((session.indicadores ?? []).map((i) => [i.kind, i]));
  const present: string[] = [];
  const slots = TRACE_SLOTS.map((kind) => {
    const Icon = INDICATOR_ICONS[kind];
    const hit = byKind.get(kind);
    const isModel = kind === "atipico_modelo_poblacional" && (hit || session.estado_modelo === "con_marca");
    let cls = "trace-slot is-empty";
    let state = "sin indicador";
    if (isModel) {
      cls = "trace-slot is-model";
      state = "marcada por el modelo";
    } else if (hit?.prioriza) {
      cls = "trace-slot is-hit";
      state = "prioriza la revisión";
    } else if (hit) {
      cls = "trace-slot is-soft";
      state = "permitido por las reglas";
    }
    if (isModel || hit) present.push(indicatorLabel(kind));
    return (
      <span key={kind} className={cls} title={`${indicatorLabel(kind)}: ${state}`} aria-hidden="true">
        <Icon size={14} strokeWidth={2} />
      </span>
    );
  });
  return (
    <span className="trace">
      {slots}
      <span className="sr-only">{present.length ? `Indicadores: ${present.join(", ")}` : "Sin indicadores"}</span>
    </span>
  );
}

export function TraceLegend() {
  return (
    <div className="legend" aria-hidden="true">
      <span>
        <i className="sw sw-hit" /> Prioriza la revisión
      </span>
      <span>
        <i className="sw sw-soft" /> Permitido por las reglas
      </span>
      <span>
        <i className="sw sw-model" /> Marca del modelo
      </span>
    </div>
  );
}

/* ---------- chips ---------- */

const REVIEW_CHIP: Record<string, string> = {
  sin_revision: "chip",
  revisada: "chip chip-ok",
  validacion_pendiente: "chip chip-warn",
};

export function ReviewChip({ status }: { status: ReviewStatus | string }) {
  return <span className={REVIEW_CHIP[status] ?? "chip"}>{REVIEW_STATUS_LABELS[status] ?? status}</span>;
}

export function ExamStateChip({ closed }: { closed: boolean }) {
  return closed ? (
    <span className="chip">Cerrada</span>
  ) : (
    <span className="chip chip-live">
      <span className="live-dot" aria-hidden="true" />
      Abierta
    </span>
  );
}

/* ---------- carga y vacíos ---------- */

export function Loading({ label = "Cargando…" }: { label?: string }) {
  return (
    <p className="loading-line" role="status">
      <Loader2 size={16} className="spin" aria-hidden="true" />
      {label}
    </p>
  );
}

export function SkeletonRows({ rows = 4, height = 56 }: { rows?: number; height?: number }) {
  return (
    <div aria-hidden="true" style={{ display: "grid", gap: 8 }}>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="skeleton" style={{ height }} />
      ))}
    </div>
  );
}

export function EmptySimple({ icon: Icon, title, children }: { icon: LucideIcon; title: string; children?: ReactNode }) {
  return (
    <div className="empty-simple">
      <Icon size={28} strokeWidth={1.6} aria-hidden="true" />
      <strong>{title}</strong>
      {children}
    </div>
  );
}

/* ---------- diálogo de confirmación (dialog nativo: foco atrapado y Esc por el navegador) ---------- */

export function ConfirmDialog({
  open,
  title,
  children,
  confirmLabel,
  cancelLabel = "Cancelar",
  tone = "primary",
  busy = false,
  dark = false,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  children?: ReactNode;
  confirmLabel: string;
  cancelLabel?: string;
  tone?: "primary" | "danger";
  busy?: boolean;
  dark?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const ref = useRef<HTMLDialogElement | null>(null);
  const confirmRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) {
      d.showModal();
      confirmRef.current?.focus();
    } else if (!open && d.open) d.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      className={`dialog${dark ? " on-black" : ""}`}
      aria-labelledby="dlg-title"
      onCancel={(e) => {
        e.preventDefault();
        if (!busy) onCancel();
      }}
      onClick={(e) => {
        if (e.target === ref.current && !busy) onCancel(); // clic en el fondo
      }}
    >
      <div className="dialog-body">
        <h2 id="dlg-title">{title}</h2>
        {children}
      </div>
      <div className="dialog-actions">
        <button type="button" className="btn btn-ghost" onClick={onCancel} disabled={busy}>
          {cancelLabel}
        </button>
        <button
          ref={confirmRef}
          type="button"
          className={`btn ${tone === "danger" ? "btn-danger" : "btn-primary"}`}
          onClick={onConfirm}
          disabled={busy}
        >
          {busy && <Loader2 size={15} className="spin" aria-hidden="true" />}
          {confirmLabel}
        </button>
      </div>
    </dialog>
  );
}

/** Nivel de un indicador como tres barritas + palabra. */
export function Level({ level }: { level: string }) {
  const n = level === "high" ? 3 : level === "medium" ? 2 : 1;
  const word = level === "high" ? "alto" : level === "medium" ? "medio" : "bajo";
  return (
    <span className="level" aria-label={`Nivel ${word}`}>
      {[1, 2, 3].map((i) => (
        <i key={i} className={i <= n ? "on" : ""} />
      ))}
      <em>nivel {word}</em>
    </span>
  );
}

/** Fecha corta y legible ("hoy 14:32", "ayer 09:10", "12 nov 18:05"). */
export function shortWhen(iso: string, now: Date = new Date()): string {
  const hasZone = /(Z|[+-]\d{2}:?\d{2})$/.test(iso);
  const d = new Date(hasZone ? iso : `${iso}Z`);
  const hm = d.toLocaleTimeString("es-AR", { hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
  const day = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diff = Math.round((day(now) - day(d)) / 86_400_000);
  if (diff === 0) return `hoy ${hm}`;
  if (diff === 1) return `ayer ${hm}`;
  const dm = d.toLocaleDateString("es-AR", { day: "numeric", month: "short" }).replace(".", "");
  return d.getFullYear() === now.getFullYear() ? `${dm} ${hm}` : `${dm} ${d.getFullYear()}`;
}
