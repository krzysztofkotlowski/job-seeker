import { createContext } from "react";
import type Keycloak from "keycloak-js";

export interface AuthConfig {
  enabled: boolean;
  url?: string;
  realm?: string;
}

export interface AuthState {
  config: AuthConfig | null;
  keycloak: Keycloak | null;
  authenticated: boolean;
  login: () => void;
  logout: () => void;
  getToken: () => Promise<string | null>;
}

export const AuthContext = createContext<AuthState | null>(null);
