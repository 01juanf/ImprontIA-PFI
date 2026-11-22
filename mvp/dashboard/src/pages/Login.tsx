import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { AlertCircle, ArrowRight, CheckCircle2, Loader2 } from "lucide-react";
import { api, getToken, setToken } from "../api";
import { usePageTitle } from "../a11y";
import { safeNextPath } from "../format";
import VersionTag from "../VersionTag";
import { BrandMark, Wordmark } from "../ui";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const [params] = useSearchParams();
  // RF17: aviso que deja DeleteAccount después de eliminar la cuenta.
  const notice = (useLocation().state as { msg?: string } | null)?.msg ?? null;
  // Problema 12: después del login se vuelve a la ruta pedida (solo rutas internas).
  const next = safeNextPath(params.get("next"));
  usePageTitle("Ingreso docente");
  // Evaluación de usabilidad, corrida 2: tras un error el foco vuelve al email.
  const emailRef = useRef<HTMLInputElement | null>(null);
  useEffect(() => {
    if (error) emailRef.current?.focus();
  }, [error]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const { access_token } = await api.login(email, password);
      setToken(access_token);
      navigate(next, { replace: true });
    } catch {
      setError("El email o la contraseña no coinciden. Revisalos e intentá de nuevo.");
    } finally {
      setLoading(false);
    }
  }

  const alreadyIn = getToken() && !loading;

  return (
    <div className="auth">
      <aside className="auth-brand on-black glow">
        <Wordmark to="/" size={26} />
        <BrandMark size={300} stroke={1.15} draw className="big-mark" />
        <div className="auth-brand-body">
          <blockquote>
            Los indicadores te dicen <span>dónde mirar</span>. Lo que significan lo decidís vos.
          </blockquote>
          <p className="auth-brand-foot">
            Ninguna sesión se sanciona de forma automática: cada marca llega con su evidencia y queda registrada tu
            revisión.
          </p>
        </div>
      </aside>

      <main className="auth-form">
        <div className="auth-card enter">
          <span className="eyebrow">Panel docente</span>
          {alreadyIn ? (
            <>
              <h1>Ya iniciaste sesión</h1>
              <p className="lead">Tu sesión docente sigue activa.</p>
              <Link className="btn btn-primary btn-large btn-block" to={next}>
                Ir al panel
                <ArrowRight size={17} aria-hidden="true" />
              </Link>
            </>
          ) : (
            <form onSubmit={handleSubmit}>
              <h1>Ingresá a tu panel</h1>
              <p className="lead">Con el email y la contraseña de tu cuenta docente.</p>

              {notice && !error && (
                <div className="alert alert-success" role="status">
                  <CheckCircle2 size={17} aria-hidden="true" />
                  <span className="alert-body">{notice}</span>
                </div>
              )}
              {error && (
                <div className="alert alert-error" role="alert">
                  <AlertCircle size={17} aria-hidden="true" />
                  <span className="alert-body">{error}</span>
                </div>
              )}

              <label className="field">
                <span className="field-label">Email</span>
                <input
                  ref={emailRef}
                  type="email"
                  autoComplete="username"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  autoFocus
                />
              </label>
              <label className="field">
                <span className="field-label">Contraseña</span>
                <input
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
              </label>

              <button type="submit" className="btn btn-primary btn-large btn-block" disabled={loading}>
                {loading && <Loader2 size={16} className="spin" aria-hidden="true" />}
                {loading ? "Ingresando…" : "Ingresar"}
              </button>
            </form>
          )}
          <div className="auth-alt">
            <span>
              ¿Sos estudiante? <Link to="/rendir">Ingresá con el código del examen</Link>
            </span>
            <VersionTag as="p" />
          </div>
        </div>
      </main>
    </div>
  );
}
