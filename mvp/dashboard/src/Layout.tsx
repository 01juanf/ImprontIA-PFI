import { useEffect, useRef, useState } from "react";
import { Navigate, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { ClipboardList, LogOut, ShieldAlert, UserRound } from "lucide-react";
import { UNAUTHORIZED_EVENT, api, clearToken, getToken } from "./api";
import { focusMainHeading } from "./a11y";
import VersionTag from "./VersionTag";
import { Wordmark } from "./ui";

/** Evento que emiten las pantallas cuando cambia algo que afecta al contador de la barra. */
export const REVIEWS_CHANGED_EVENT = "improntia:revisiones";

function loginUrl(pathname: string, search: string): string {
  return `/login?next=${encodeURIComponent(pathname + search)}`;
}

export function RequireAuth() {
  const location = useLocation();
  // Problema 12: después del login se vuelve al enlace pedido.
  if (!getToken()) return <Navigate to={loginUrl(location.pathname, location.search)} replace />;
  return <Outlet />;
}

export default function Layout() {
  const navigate = useNavigate();
  const location = useLocation();
  const [pending, setPending] = useState<number | null>(null);
  const [tick, setTick] = useState(0);
  const mainRef = useRef<HTMLElement | null>(null);
  const firstRender = useRef(true);

  // Contador de casos con validación adicional pendiente (RF11/HU08); se refresca al navegar
  // y cuando una pantalla avisa que registró una revisión (problema 13).
  useEffect(() => {
    api
      .listSessions({ review_status: "validacion_pendiente" })
      .then((s) => setPending(s.length))
      .catch(() => setPending(null));
  }, [location.pathname, tick]);

  useEffect(() => {
    const onChange = () => setTick((n) => n + 1);
    window.addEventListener(REVIEWS_CHANGED_EVENT, onChange);
    return () => window.removeEventListener(REVIEWS_CHANGED_EVENT, onChange);
  }, []);

  // Token vencido o inválido (401): al login, conservando la ruta actual.
  useEffect(() => {
    const onUnauthorized = () => navigate(loginUrl(window.location.pathname, window.location.search), { replace: true });
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, [navigate]);

  // Problema 11: después de una navegación interna, el foco va al encabezado de la pantalla.
  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    window.scrollTo(0, 0);
    const id = window.setTimeout(() => focusMainHeading(mainRef.current), 50);
    return () => window.clearTimeout(id);
  }, [location.pathname]);

  function logout() {
    clearToken();
    navigate("/login");
  }

  // Problema 7: el detalle de una sesión pertenece a «Evaluaciones».
  const inExams = location.pathname.startsWith("/exams") || location.pathname.startsWith("/sessions/");

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Wordmark to="/exams" />
        <nav className="sidenav" aria-label="Navegación principal">
          <span className="sidenav-label">Panel docente</span>
          <NavLink to="/exams" className={() => (inExams ? "active" : "")} aria-current={inExams ? "page" : undefined}>
            <ClipboardList size={18} aria-hidden="true" />
            <span className="nav-text">Evaluaciones</span>
          </NavLink>
          <NavLink
            to="/validaciones"
            aria-label={pending ? `Validaciones pendientes (${pending})` : "Validaciones pendientes"}
          >
            <ShieldAlert size={18} aria-hidden="true" />
            <span className="nav-text">Validaciones</span>
            {pending !== null && pending > 0 && (
              <span className="count-pill" aria-hidden="true">
                {pending}
              </span>
            )}
          </NavLink>
        </nav>
        <div className="sidebar-foot">
          <NavLink to="/cuenta" className="side-btn" aria-label="Tu cuenta">
            <UserRound size={18} aria-hidden="true" />
            <span className="side-label">Tu cuenta</span>
          </NavLink>
          <button className="side-btn" onClick={logout} aria-label="Cerrar sesión">
            <LogOut size={18} aria-hidden="true" />
            <span className="side-label">Cerrar sesión</span>
          </button>
          <VersionTag as="p" />
        </div>
      </aside>
      <main ref={mainRef} className="main">
        <Outlet />
      </main>
    </div>
  );
}
