// src/useAuth.js
import { useEffect, useState, useCallback } from 'react';

export function useAuth() {
  const [user, setUser] = useState(null);        // {email, name, picture, sub} or null
  const [authLoading, setAuthLoading] = useState(true);

  const doFetchMe = useCallback(async (signal) => {
    try {
      const r = await fetch('/api/auth/me', {
        credentials: 'include',
        signal,
      });
      if (!r.ok) {
        const t = await r.text().catch(() => '');
        console.error('/api/auth/me failed', r.status, t);
        setUser(null);
        return;
      }
      const j = await r.json();
      // backend returns {} when logged out
      setUser(j && Object.keys(j).length ? j : null);
    } catch (e) {
      console.error('/api/auth/me error', e);
      setUser(null);
    }
  }, []);

  const refresh = useCallback(async () => {
    setAuthLoading(true);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 8000); // stop a “forever pending” request
    try {
      await doFetchMe(controller.signal);
    } finally {
      clearTimeout(timer);
      setAuthLoading(false);
    }
  }, [doFetchMe]);

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 8000);

    (async () => {
      try {
        await doFetchMe(controller.signal);
      } finally {
        if (!cancelled) setAuthLoading(false);
        clearTimeout(timer);
      }
    })();

    return () => {
      cancelled = true;
      clearTimeout(timer);
      controller.abort();
    };
  }, [doFetchMe]);

  const login = () => {
    // Sends the browser to FastAPI → Google → back to FRONTEND_ORIGIN
    window.location.href = '/api/auth/google';
  };

  const logout = async () => {
    try {
      await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' });
    } catch (e) {
      console.error('logout error', e);
    } finally {
      setUser(null);
      // optional: refresh to confirm server session is cleared
      refresh();
    }
  };

  return { user, authLoading, login, logout, refresh };
}
