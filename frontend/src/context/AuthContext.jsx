import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, clearSession, loadSession, onUnauthorized, saveSession } from "../api/client";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [session, setSession] = useState(() => loadSession());
  const [checking, setChecking] = useState(Boolean(loadSession()));

  const logout = useCallback(() => {
    clearSession();
    setSession(null);
  }, []);

  useEffect(() => onUnauthorized(() => setSession(null)), []);

  // Validate a stored session once (the token may have expired while the tab was closed).
  useEffect(() => {
    if (!session) return;
    api
      .me()
      .then((user) => {
        const updated = { ...session, username: user.username, role: user.role, fullName: user.full_name };
        saveSession(updated);
        setSession(updated);
      })
      .catch(() => logout())
      .finally(() => setChecking(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const login = useCallback(async (username, password) => {
    const data = await api.login(username, password);
    const next = { token: data.access_token, username: data.username, role: data.role };
    saveSession(next);
    setSession(next);
    return next;
  }, []);

  const value = useMemo(
    () => ({
      user: session,
      checking,
      login,
      logout,
      isAdmin: session?.role === "admin",
      canUpload: session?.role === "admin" || session?.role === "editor",
    }),
    [session, checking, login, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);
