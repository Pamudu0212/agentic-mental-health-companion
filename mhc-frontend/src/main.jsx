// src/main.jsx
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import "./index.css";
import App from "./App.jsx";
import { useAuth } from "./useAuth";
import ProfileSetup from "./ProfileSetup.jsx";

function LoginScreen() {
  const { login } = useAuth();
  return (
    <div className="min-h-screen grid place-items-center bg-gradient-to-br from-emerald-50 via-teal-50 to-sky-50">
      <div className="bg-white/90 p-8 rounded-2xl shadow border border-emerald-100">
        <h1 className="text-xl font-semibold text-slate-800">Sign in</h1>
        <p className="text-slate-600 text-sm mt-1">
          Sign in with Google to continue.
        </p>
        <button
          onClick={login}
          className="mt-4 rounded-xl bg-emerald-600 text-white px-5 py-2 font-medium hover:bg-emerald-700 transition"
        >
          Continue with Google
        </button>
      </div>
    </div>
  );
}

function Gate() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen grid place-items-center text-slate-600">
        <div className="flex items-center gap-2">
          <div className="h-4 w-4 rounded-full bg-emerald-400 animate-pulse" />
          <span>Loading…</span>
        </div>
      </div>
    );
  }

  if (!user) {
    return <LoginScreen />;
  }

  if (!user.profile_complete) {
    return <ProfileSetup user={user} />;
  }

  // Authenticated and profile complete → companion
  return <App />;
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/*" element={<Gate />} />
        {/* you can add /settings etc later */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>
);