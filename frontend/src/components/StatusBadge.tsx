import type { JobStatus } from "../api/types";

const STATUS_CONFIG: Record<JobStatus, { label: string; bg: string; text: string }> = {
  new: { label: "New", bg: "bg-blue-100", text: "text-blue-800" },
  applied: { label: "Applied", bg: "bg-yellow-100", text: "text-yellow-800" },
  interview: { label: "Interview", bg: "bg-purple-100", text: "text-purple-800" },
  offer: { label: "Offer", bg: "bg-green-100", text: "text-green-800" },
  rejected: { label: "Rejected", bg: "bg-red-100", text: "text-red-800" },
};

export function StatusBadge({ status }: { status: JobStatus }) {
  const cfg = STATUS_CONFIG[status] ?? STATUS_CONFIG.new;
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${cfg.bg} ${cfg.text}`}>
      {cfg.label}
    </span>
  );
}
