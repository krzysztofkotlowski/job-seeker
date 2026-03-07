import { useCallback, useEffect, useState, type ReactNode } from "react";
import Keycloak from "keycloak-js";
import { AuthContext } from "./auth-context";
import type { AuthConfig, AuthState } from "./auth-context";
import { setTokenProvider } from "./tokenProvider";

export type { AuthConfig, AuthState } from "./auth-context";

const AUTH_CONFIG_URL = "/api/v1/auth/config";
const CLIENT_ID = "jobseeker-frontend";

function hasOAuthCallbackParams(): boolean {
  const params = new URLSearchParams(window.location.search);
  return params.has("code") && params.has("state");
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<AuthConfig | null>(null);
  const [keycloak, setKeycloak] = useState<Keycloak | null>(null);
  const [authenticated, setAuthenticated] = useState(false);

  useEffect(() => {
    fetch(AUTH_CONFIG_URL)
      .then((r) => {
        if (!r.ok) throw new Error("Auth config failed");
        return r.json();
      })
      .then((data: AuthConfig) => {
        setConfig(data);
        if (!data.enabled || !data.url || !data.realm) return;

        // Only init Keycloak when returning from login (OAuth callback in URL)
        if (!hasOAuthCallbackParams()) return;

        const kc = new Keycloak({
          url: data.url,
          realm: data.realm,
          clientId: CLIENT_ID,
        });
        kc.init({
          onLoad: "check-sso",
          checkLoginIframe: false,
        })
          .then((auth) => {
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
          })
          .catch(() => {
            setConfig((c) =>
              c ? { ...c, enabled: false } : { enabled: false },
            );
            setTokenProvider(null);
          });
      })
      .catch(() => {
        setConfig({ enabled: false });
        setTokenProvider(null);
      });
  }, []);

  const login = useCallback(() => {
    if (keycloak) {
      keycloak.login();
      return;
    }
    if (!config?.enabled || !config.url || !config.realm) return;

    const kc = new Keycloak({
      url: config.url,
      realm: config.realm,
      clientId: CLIENT_ID,
    });
    kc.init({
      onLoad: "login-required",
      checkLoginIframe: false,
    }).catch(() => {
      setConfig((c) => (c ? { ...c, enabled: false } : { enabled: false }));
      setTokenProvider(null);
    });
    // init with login-required redirects to Keycloak; page unloads before redirect
  }, [keycloak, config]);

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
