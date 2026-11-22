import { versionLabel } from "./version";

declare const __APP_VERSION__: string;

/**
 * Versión y commit con los que se compiló el dashboard (paquete de reproducibilidad).
 * En el panel va como pie de página (`footer`); en el ingreso, dentro de la tarjeta (`p`).
 */
export default function VersionTag({ as = "footer" }: { as?: "footer" | "p" }) {
  const commit = import.meta.env.VITE_GIT_COMMIT as string | undefined;
  const label = versionLabel(__APP_VERSION__, commit);
  const Tag = as;
  return (
    <Tag className="version-tag" title={commit ? `commit ${commit}` : undefined}>
      {label}
    </Tag>
  );
}
