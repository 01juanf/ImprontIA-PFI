import { ReviewChip } from "./ui";

/** Compatibilidad: el chip de estado de revisión vive ahora en ui.tsx. */
export default function ReviewStatusBadge({ status }: { status: string }) {
  return <ReviewChip status={status} />;
}
