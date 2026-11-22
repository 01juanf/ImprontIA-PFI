import { Link } from "react-router-dom";
import { ArrowRight, ClipboardList, PenLine } from "lucide-react";
import { getToken } from "../api";
import { usePageTitle } from "../a11y";
import { Wordmark } from "../ui";
import CodeEntry from "../CodeEntry";
import VersionTag from "../VersionTag";

/** Inicio público: cada perfil encuentra su camino sin saber las rutas. */
export default function Home() {
  usePageTitle(null);
  const teacher = Boolean(getToken());

  return (
    <div className="home on-black glow">
      <header className="home-top">
        <Wordmark size={26} />
        <Link className="btn btn-quiet btn-small" to={teacher ? "/exams" : "/login"}>
          {teacher ? "Ir al panel" : "Ingreso docente"}
        </Link>
      </header>

      <main className="home-main">
        <div className="home-hero enter">
          <span className="eyebrow">Evaluaciones digitales con evidencia de proceso</span>
          <h1>
            Evidencia para revisar, <span>no veredictos.</span>
          </h1>
          <p>
            Durante el examen, ImprontIA registra cómo se escribió la respuesta: ritmo de tecleo, texto pegado y
            cambios de pestaña. Al docente le muestra qué entregas mirar primero y por qué. La decisión siempre es suya.
          </p>
        </div>

        <div className="paths">
          <section className="path enter" aria-labelledby="p-est" style={{ animationDelay: "60ms" }}>
            <div className="path-head">
              <span className="path-icon">
                <PenLine size={19} aria-hidden="true" />
              </span>
              <h2 id="p-est">Voy a rendir</h2>
            </div>
            <p>Ingresá el código que te compartió tu docente. Antes de empezar vas a ver exactamente qué se registra.</p>
            <CodeEntry />
          </section>

          <section className="path enter" aria-labelledby="p-doc" style={{ animationDelay: "110ms" }}>
            <div className="path-head">
              <span className="path-icon">
                <ClipboardList size={19} aria-hidden="true" />
              </span>
              <h2 id="p-doc">Soy docente</h2>
            </div>
            <p>Creá una evaluación, compartí el código y revisá la evidencia de cada entrega.</p>
            <Link className="btn btn-ghost btn-large" to={teacher ? "/exams" : "/login"}>
              {teacher ? "Ir al panel" : "Ingresar al panel"}
              <ArrowRight size={17} aria-hidden="true" />
            </Link>
          </section>
        </div>

        <ol className="how" aria-label="Cómo funciona">
          <li>
            <span className="num">01 · antes</span>
            <strong>Consentimiento informado</strong>
            El estudiante ve qué señales se registran y acepta antes de ver la consigna.
          </li>
          <li>
            <span className="num">02 · durante</span>
            <strong>Captura de metadatos</strong>
            Tiempos de tecleo, pegado y foco de la pestaña. Nunca qué teclas ni el texto pegado.
          </li>
          <li>
            <span className="num">03 · después</span>
            <strong>Revisión docente</strong>
            Indicadores explicados, comparación con la cohorte y constancia de cada revisión.
          </li>
        </ol>
      </main>

      <footer className="home-foot">
        <span>ImprontIA · Proyecto Final de Ingeniería</span>
        <VersionTag as="p" />
      </footer>
    </div>
  );
}
