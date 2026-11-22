import { Link } from "react-router-dom";
import { usePageTitle } from "../a11y";
import { getToken } from "../api";
import { Wordmark } from "../ui";

/** Página «No encontrada» (evaluación de usabilidad, problema 12): reemplaza la redirección silenciosa. */
export default function NotFound() {
  usePageTitle("Página no encontrada");
  const teacher = Boolean(getToken());
  return (
    <div className="student on-black glow">
      <header className="student-bar">
        <Wordmark to="/" />
      </header>
      <main className="student-main enter">
        <span className="eyebrow">Error 404</span>
        <h1>Página no encontrada</h1>
        <p className="lead">La dirección no corresponde a ninguna pantalla de ImprontIA.</p>
        <div className="btn-row" style={{ marginTop: 24 }}>
          <Link className="btn btn-primary btn-large" to={teacher ? "/exams" : "/login"}>
            {teacher ? "Ir a Evaluaciones" : "Ingresar como docente"}
          </Link>
          <Link className="btn btn-ghost btn-large" to="/rendir">
            Ingresar a un examen
          </Link>
        </div>
      </main>
    </div>
  );
}
