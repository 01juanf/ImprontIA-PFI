import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Trash2 } from "lucide-react";
import { ApiError, api, clearToken } from "./api";
import { useFocusWhen } from "./a11y";

/**
 * RF17: el docente elimina su cuenta (DELETE /auth/me). Se borran todas sus evaluaciones con
 * sus sesiones, eventos, métricas, indicadores y revisiones. Pide la contraseña y una
 * confirmación explícita; después cierra la sesión y vuelve al ingreso con un aviso.
 */
export default function DeleteAccount() {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const passwordRef = useFocusWhen<HTMLInputElement>(open);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setDeleting(true);
    try {
      await api.deleteAccount(password);
      clearToken();
      navigate("/login", { replace: true, state: { msg: "Tu cuenta y todos sus datos se eliminaron." } });
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 401
          ? "Contraseña incorrecta."
          : "No se pudo eliminar la cuenta. Reintentá en unos segundos.",
      );
      setDeleting(false);
      passwordRef.current?.focus();
    }
  }

  return (
    <section className="danger-zone" aria-labelledby="cuenta-titulo" style={{ display: "block" }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 16, flexWrap: "wrap", alignItems: "center" }}>
        <div>
          <h3 id="cuenta-titulo">Eliminar la cuenta</h3>
          <p>
            Borra todas tus evaluaciones, con sus sesiones, eventos, métricas, indicadores y revisiones. No se puede
            deshacer.
          </p>
        </div>
        {!open && (
          <button className="btn btn-ghost" onClick={() => setOpen(true)}>
            <Trash2 size={15} aria-hidden="true" />
            Eliminar mi cuenta…
          </button>
        )}
      </div>
      {open && (
        <form onSubmit={handleSubmit} style={{ marginTop: 16, maxWidth: 420 }}>
          {error && (
            <div className="alert alert-error" role="alert">
              {error}
            </div>
          )}
          <label className="field">
            <span className="field-label">Contraseña actual (para confirmar)</span>
            <input
              ref={passwordRef}
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </label>
          <div className="btn-row">
            <button type="submit" className="btn btn-danger" disabled={deleting || !password}>
              {deleting ? "Eliminando…" : "Eliminar mi cuenta definitivamente"}
            </button>
            <button
              type="button"
              className="btn btn-quiet"
              onClick={() => {
                setOpen(false);
                setPassword("");
                setError(null);
              }}
            >
              Cancelar
            </button>
          </div>
        </form>
      )}
    </section>
  );
}
