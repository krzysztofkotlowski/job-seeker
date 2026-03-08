import type React from "react";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";

export interface ChartTooltipProps {
  active?: boolean;
  payload?: readonly unknown[];
  label?: string | number;
  /** Recharts-compatible formatter: (value, name, item) => [displayValue, displayName] or displayValue */
  formatter?: (
    value: unknown,
    name?: string,
    item?: unknown
  ) => [React.ReactNode, React.ReactNode] | React.ReactNode;
}

/** Shared tooltip styling for all Recharts charts - Paper with Typography. */
export function ChartTooltip({
  active,
  payload,
  label,
  formatter,
}: ChartTooltipProps) {
  if (!active || !payload?.length) return null;

  return (
    <Paper
      sx={{
        p: 1.5,
        borderRadius: 1,
        boxShadow: 2,
      }}
    >
      {label != null && String(label) !== "" && (
        <Typography variant="body2" fontWeight={600} sx={{ mb: 0.5 }}>
          {label}
        </Typography>
      )}
      {payload.map((item: unknown, i: number) => {
        const it = item as { name?: string; value?: string | number };
        let displayValue: React.ReactNode = String(it.value ?? "");
        let displayName: React.ReactNode = it.name ?? "";
        if (formatter) {
          const result = formatter(it.value, it.name, item);
          if (Array.isArray(result)) {
            [displayValue, displayName] = result;
          } else {
            displayValue = result;
          }
        }
        return (
          <Typography
            key={i}
            variant="body2"
            color="text.secondary"
            sx={{ "&:not(:last-child)": { mb: 0.25 } }}
          >
            {displayName ? `${String(displayName)}: ` : ""}
            {displayValue}
          </Typography>
        );
      })}
    </Paper>
  );
}
