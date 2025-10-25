// src/ProfileSetup.jsx
import { useState } from "react";
import { useAuth } from "./useAuth";

export default function ProfileSetup({ user }) {
  const [name, setName] = useState(user?.name || "");
  const [timezone, setTimezone] = useState(user?.timezone || "Asia/Colombo");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");
  const { refresh } = useAuth();

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setErr("");
    try {
      const r = await fetch("/api/user/profile", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ name, timezone }),
      });
      if (!r.ok) throw new Error(await r.text());
      // Refresh auth state to detect profile completion
      await refresh();
    } catch (e) {
      setErr(e.message || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="min-h-screen grid place-items-center bg-gradient-to-br from-emerald-50 via-teal-50 to-sky-50">
      <div className="w-full max-w-md bg-white/90 rounded-2xl p-6 shadow-lg border border-emerald-100">
        <h1 className="text-xl font-semibold text-slate-800">Welcome 👋</h1>
        <p className="text-slate-600 text-sm mt-1">
          Let's complete your profile so we can personalize your experience.
        </p>

        <form onSubmit={submit} className="mt-4 space-y-3">
          <div>
            <label className="text-sm text-slate-600">Name</label>
            <input
              className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-emerald-400"
              value={name}
              onChange={e => setName(e.target.value)}
              required
            />
          </div>
          <div>
            <label className="text-sm text-slate-600">Time zone</label>
            <input
              className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-emerald-400"
              value={timezone}
              onChange={e => setTimezone(e.target.value)}
              placeholder="e.g. Asia/Colombo"
              required
            />
          </div>
          {err && <div className="text-rose-600 text-sm">{err}</div>}
          <button
            type="submit"
            disabled={saving}
            className="w-full mt-2 rounded-xl bg-emerald-600 text-white py-2 font-medium hover:bg-emerald-700 disabled:opacity-50 transition"
          >
            {saving ? "Saving..." : "Continue"}
          </button>
        </form>

        <div className="mt-3 text-xs text-slate-500">
          You can change these later in Settings.
        </div>
      </div>
    </div>
  );
}