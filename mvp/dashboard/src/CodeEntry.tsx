import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { normalizeJoinCode } from "./examDraft";

/**
 * Ingreso del estudiante con solo el código del examen (evaluación de usabilidad, problema 2).
 * Navega a la ruta del examen (/exam/:joinCode), que valida el código.
 */
export default function CodeEntry({ autoFocus = false }: { autoFocus?: boolean }) {
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const normalized = normalizeJoinCode(code);
    if (!normalized) {
      setError("Ingresá el código de examen que te dio tu docente.");
      return;
    }
    navigate(`/exam/${encodeURIComponent(normalized)}`);
  }

  return (
    <form onSubmit={handleSubmit} noValidate>
      {error && (
        <div className="alert alert-error" role="alert">
          {error}
        </div>
      )}
      <label htmlFor="join-code" className="sr-only">
        Código de examen
      </label>
      <div className="code-entry">
        <input
          id="join-code"
          name="code"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          placeholder="Código, ej. AB12CD"
          autoComplete="off"
          autoCapitalize="characters"
          spellCheck={false}
          maxLength={12}
          autoFocus={autoFocus}
        />
        <button type="submit" className="btn btn-primary btn-large">
          Continuar
          <ArrowRight size={17} aria-hidden="true" />
        </button>
      </div>
    </form>
  );
}
