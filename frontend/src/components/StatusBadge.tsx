import Chip from "@mui/material/Chip";
import type { JobStatus } from "../api/types";
import { STATUS_CONFIG } from "../utils/job";

export function StatusBadge({ status }: { status: JobStatus }) {
  const cfg = STATUS_CONFIG[status] ?? STATUS_CONFIG.new;
  return (
    <Chip
      label={cfg.label}
      size="small"
      color={cfg.color}
      variant="filled"
      sx={{ height: 22, fontSize: 11, fontWeight: 600 }}
    />
  );
}
