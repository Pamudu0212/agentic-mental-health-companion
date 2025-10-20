// src/TopBar.jsx
import React from 'react';
import { useAuth } from './useAuth';

export default function TopBar() {
  const { user, loading, login, logout } = useAuth();

  if (loading) {
    return (
      <div style={{ padding: 12, borderBottom: '1px solid #eee' }}>
        <span>Loading…</span>
      </div>
    );
  }

  return (
    <div style={{
      padding: 12, borderBottom: '1px solid #eee',
      display: 'flex', alignItems: 'center', justifyContent: 'space-between'
    }}>
      <div style={{ fontWeight: 600 }}>Mental Health Companion</div>

      {user ? (
        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          {user.picture ? (
            <img src={user.picture} alt="" width={28} height={28} style={{ borderRadius: 999 }} />
          ) : null}
          <span>{user.name || user.email}</span>
          <button onClick={logout}>Logout</button>
        </div>
      ) : (
        <button onClick={login}>Login with Google</button>
      )}
    </div>
  );
}
