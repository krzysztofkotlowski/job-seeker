import Chip from "@mui/material/Chip";
import type { JobStatus } from "../api/types";

const STATUS_CONFIG: Record<JobStatus, { label: string; color: "primary" | "warning" | "success" | "error" | "info" | "default" }> = {
  new: { label: "New", color: "primary" },
  seen: { label: "Seen", color: "default" },
  applied: { label: "Applied", color: "warning" },
  interview: { label: "Interview", color: "info" },
  offer: { label: "Offer", color: "success" },
  rejected: { label: "Rejected", color: "error" },
};

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
