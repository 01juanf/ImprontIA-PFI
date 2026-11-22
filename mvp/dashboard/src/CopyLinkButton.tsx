import { useEffect, useRef, useState } from "react";
import { Check, Link2 } from "lucide-react";
import { studentExamUrl } from "./examDraft";

async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // se intenta el método alternativo
  }
  try {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(ta);
    return ok;
  } catch {
    return false;
  }
}

/**
 * Botón «Copiar enlace» del examen para estudiantes (evaluación de usabilidad, problema 3).
 * Copia la URL absoluta y anuncia el resultado en una región aria-live.
 */
export default function CopyLinkButton({
  joinCode,
  examName,
  compact = false,
  dark = false,
}: {
  joinCode: string;
  examName?: string;
  compact?: boolean;
  dark?: boolean;
}) {
  const url = studentExamUrl(window.location.origin, joinCode);
  const [state, setState] = useState<"idle" | "ok" | "error">("idle");
  const timer = useRef<number | null>(null);

  useEffect(() => () => {
    if (timer.current) window.clearTimeout(timer.current);
  }, []);

  async function handleClick() {
    const ok = await copyText(url);
    setState(ok ? "ok" : "error");
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setState("idle"), 3000);
  }

  const Icon = state === "ok" ? Check : Link2;
  return (
    <span className={`copy-link${dark ? " on-black" : ""}`} style={dark ? { background: "transparent" } : undefined}>
      <button
        type="button"
        className={`btn ${dark ? "btn-primary" : "btn-quiet"} btn-small${compact ? " btn-icon" : ""}`}
        onClick={handleClick}
        title={`Copiar ${url}`}
        aria-label={`Copiar enlace para estudiantes${examName ? ` de ${examName}` : ""}`}
        data-url={url}
      >
        <Icon size={15} aria-hidden="true" />
        {!compact && (state === "ok" ? "Copiado" : "Copiar enlace")}
      </button>
      <span className={compact ? "sr-only" : "sr-only"} role="status" aria-live="polite">
        {state === "ok" ? "Enlace copiado" : state === "error" ? `No se pudo copiar: ${url}` : ""}
      </span>
      {state === "error" && <span className="copy-feedback" style={{ color: "var(--danger)" }}>No se pudo copiar</span>}
    </span>
  );
}
