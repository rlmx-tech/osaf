import { createContext, useContext, useState, useCallback, useEffect } from "react";
import client from "./client";

const AuthContext = createContext(null);

const STORAGE_KEY = "osaf_auth";

function loadStored() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export function AuthProvider({ children }) {
  const [auth, setAuth] = useState(() => loadStored());

  // Set axios auth header when token changes
  useEffect(() => {
    if (auth?.access_token) {
      client.defaults.headers.common["Authorization"] = `Bearer ${auth.access_token}`;
    } else {
      delete client.defaults.headers.common["Authorization"];
    }
  }, [auth]);

  const login = useCallback(async (username, password) => {
    const params = new URLSearchParams();
    params.append("username", username);
    params.append("password", password);
    const res = await client.post("/auth/login", params, {
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    });
    const data = res.data;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
    setAuth(data);
    return data;
  }, []);

  const register = useCallback(async (userData) => {
    const res = await client.post("/auth/register", userData);
    return res.data;
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    setAuth(null);
    delete client.defaults.headers.common["Authorization"];
  }, []);

  const value = {
    user: auth?.user || null,
    token: auth?.access_token || null,
    isAuthenticated: !!auth?.access_token,
    isAdmin: auth?.user?.role === "admin",
    isContributor: auth?.user?.role === "verified_contributor" || auth?.user?.role === "admin",
    login,
    register,
    logout,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
