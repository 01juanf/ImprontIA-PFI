import { useNavigate } from "react-router-dom";
import { LogOut } from "lucide-react";
import { clearToken } from "../api";
import { usePageTitle } from "../a11y";
import DeleteAccount from "../DeleteAccount";
import VersionTag from "../VersionTag";

/** Cuenta del docente: cerrar sesión y, separado y abajo, eliminar la cuenta (RF17). */
export default function Account() {
  usePageTitle("Tu cuenta");
  const navigate = useNavigate();
  return (
    <div className="page page-narrow">
      <div className="page-head">
        <div>
          <h1>Tu cuenta</h1>
          <p className="sub">Sesión docente activa en este navegador.</p>
        </div>
      </div>

      <section className="card">
        <div className="card-head" style={{ marginBottom: 0 }}>
          <div>
            <h3>Cerrar sesión</h3>
            <p className="panel-note" style={{ marginTop: 4 }}>
              Tus evaluaciones y revisiones quedan guardadas.
            </p>
          </div>
          <button
            className="btn btn-ghost"
            onClick={() => {
              clearToken();
              navigate("/login");
            }}
          >
            <LogOut size={15} aria-hidden="true" />
            Cerrar sesión
          </button>
        </div>
      </section>

      <DeleteAccount />
      <VersionTag as="p" />
    </div>
  );
}
