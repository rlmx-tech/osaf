import { createContext, useContext, useState, useCallback } from "react";
import client from "./client";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  // Only user profile info is stored in state — the JWT lives in an httpOnly cookie
  // and is never accessible to JavaScript.
  const [user, setUser] = useState(null);

  const login = useCallback(async (username, password) => {
    const params = new URLSearchParams();
    params.append("username", username);
    params.append("password", password);
    const res = await client.post("/auth/login", params, {
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    });
    setUser(res.data.user);
    return res.data;
  }, []);

  const register = useCallback(async (userData) => {
    const res = await client.post("/auth/register", userData);
    return res.data;
  }, []);

  const logout = useCallback(async () => {
    try {
      await client.post("/auth/logout");
    } finally {
      setUser(null);
    }
  }, []);

  const value = {
    user,
    isAuthenticated: !!user,
    isAdmin: user?.role === "admin",
    isContributor: user?.role === "verified_contributor" || user?.role === "admin",
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
