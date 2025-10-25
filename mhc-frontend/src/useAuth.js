// src/useAuth.js
import { useEffect, useState } from "react";

// Point straight at the backend, skipping the Vite proxy for auth.
// Add this in your frontend .env: VITE_BACKEND_URL=http://127.0.0.1:8000
const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || "http://127.0.0.1:8000";

export function useAuth() {
  const [user, setUser] = useState(null); // {email, name, picture, sub, profile_complete?} or null
  const [loading, setLoading] = useState(true);

  const refresh = async () => {
    setLoading(true);
    try {
      // IMPORTANT: call backend origin directly so the 8000 cookie is sent
      const res = await fetch(`${BACKEND_URL}/api/auth/me`, {
        credentials: "include",
      });
      // If CORS is correct on the backend (it is), this works.
      const data = await res.json();
      setUser(data && data.email ? data : null);
    } catch (e) {
      console.error("/api/auth/me error", e);
      setUser(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const login = () => {
    // 🚫 Do NOT go through /api on the Vite dev server.
    // ✅ Send the browser straight to the backend origin so the cookie is set for 8000.
    window.location.href = `${BACKEND_URL}/api/auth/google`;
  };

  const logout = async () => {
    try {
      await fetch(`${BACKEND_URL}/api/auth/logout`, {
        method: "POST",
        credentials: "include",
      });
    } catch (e) {
      console.error("/api/auth/logout error", e);
    } finally {
      // Clear local state and redirect to login
      setUser(null);
      // Force page reload to ensure clean state
      window.location.href = "/";
    }
  };

  return { user, loading, login, logout, refresh };
}