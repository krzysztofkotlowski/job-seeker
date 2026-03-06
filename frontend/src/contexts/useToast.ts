import { useContext } from "react";
import { ToastContext } from "./toast-context";

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    return {
      showError: (msg: string) => console.error("[Toast not available]", msg),
      showSuccess: (msg: string) => console.log("[Toast not available]", msg),
    };
  }
  return ctx;
}
