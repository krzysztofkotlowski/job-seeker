import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import Keycloak from "keycloak-js";
import { setTokenProvider } from "./tokenProvider";

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

const AuthContext = createContext<AuthState | null>(null);

const AUTH_CONFIG_URL = "/api/v1/auth/config";
const CLIENT_ID = "jobseeker-frontend";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<AuthConfig | null>(null);
  const [keycloak, setKeycloak] = useState<Keycloak | null>(null);
  const [authenticated, setAuthenticated] = useState(false);

  useEffect(() => {
    fetch(AUTH_CONFIG_URL)
      .then((r) => r.json())
      .then((data: AuthConfig) => {
        setConfig(data);
        if (!data.enabled || !data.url || !data.realm) return;
        const kc = new Keycloak({
          url: data.url,
          realm: data.realm,
          clientId: CLIENT_ID,
        });
        kc.init({ onLoad: "check-sso" }).then((auth) => {
          setKeycloak(kc);
          setAuthenticated(!!auth);
          setTokenProvider(
            auth
              ? async () => {
                  await kc.updateToken(30);
                  return kc.token ?? null;
                }
              : null,
          );
        });
      })
      .catch(() => {
        setConfig({ enabled: false });
        setTokenProvider(null);
      });
  }, []);

  const login = useCallback(() => {
    keycloak?.login();
  }, [keycloak]);

  const logout = useCallback(() => {
    keycloak?.logout();
  }, [keycloak]);

  const getToken = useCallback(async (): Promise<string | null> => {
    if (!keycloak || !authenticated) return null;
    try {
      await keycloak.updateToken(30);
      return keycloak.token ?? null;
    } catch {
      return null;
    }
  }, [keycloak, authenticated]);

  const value: AuthState = {
    config,
    keycloak,
    authenticated,
    login,
    logout,
    getToken,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState | null {
  return useContext(AuthContext);
}
