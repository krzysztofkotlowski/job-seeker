import { createContext } from "react";

export interface ToastContextValue {
  showError: (message: string) => void;
  showSuccess: (message: string) => void;
}

export const ToastContext = createContext<ToastContextValue | null>(null);
