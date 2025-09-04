// src/App.jsx
import { useEffect, useMemo, useRef, useState } from "react";
import { sendChat } from "./api";

// ---- small helper: stable per-user id in localStorage ----
function useUserId() {
  return useMemo(() => {
    const k = "mhc_user_id";
    let v = localStorage.getItem(k);
    if (!v) {
      v = "u_" + Math.random().toString(36).slice(2, 10);
      localStorage.setItem(k, v);
    }
    return v;
  }, []);
}

function Insights({ latest }) {
  const { mood, strategy, crisis_detected } = latest || {};
  return (
    <div className="bg-white border border-slate-200 rounded-2xl shadow-sm p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Insights</h2>
        {crisis_detected ? (
          <span className="px-2 py-1 text-xs rounded-full bg-red-100 text-red-700">
            Crisis detected
          </span>
        ) : (
          <span className="px-2 py-1 text-xs rounded-full bg-emerald-50 text-emerald-700">
            Safe
          </span>
        )}
      </div>

      <div>
        <div className="text-xs uppercase tracking-wide text-slate-500">Mood</div>
        <div className="mt-1 text-base font-medium text-slate-800">
          {mood || "—"}
        </div>
      </div>

      <div>
        <div className="text-xs uppercase tracking-wide text-slate-500">
          Suggested next step
        </div>
        <div className="mt-1 text-slate-800 whitespace-pre-wrap break-words">
          {strategy || "—"}
        </div>
      </div>

      <div className="text-xs text-slate-500">
        These insights are assistive, not clinical guidance.
      </div>
    </div>
  );
}

export default function App() {
  const userId = useUserId();
  const [input, setInput] = useState("");
  const [msgs, setMsgs] = useState([]); // {role, content}
  const [loading, setLoading] = useState(false);
  const [latest, setLatest] = useState(null); // {mood, strategy, crisis_detected}
  const logRef = useRef(null);

  // auto-scroll to bottom on new messages / loading state
  useEffect(() => {
    const el = logRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [msgs, loading]);

  async function onSend(e) {
    e.preventDefault();
    const text = input.trim();
    if (!text || loading) return;

    setMsgs((m) => [...m, { role: "user", content: text }]);
    setInput("");
    setLoading(true);

    try {
      const res = await sendChat(text, userId);
      // Show only the “assistant” text in chat
      setMsgs((m) => [...m, { role: "assistant", content: res.encouragement }]);

      // Update the Insights panel
      setLatest({
        mood: res.mood,
        strategy: res.strategy,
        crisis_detected: res.crisis_detected,
      });
    } catch (err) {
      const detail =
        err?.message ||
        "Something went wrong. Please try again.";
      setMsgs((m) => [
        ...m,
        { role: "assistant", content: `Error: ${detail}` },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="max-w-6xl mx-auto p-6">
        <h1 className="text-3xl font-bold mb-2">Agentic Mental Health Companion</h1>
        <p className="text-sm text-slate-600 mb-6">
          This app isn’t a medical service. If you’re in danger, contact local emergency services.
        </p>

        {/* Two-column layout */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Chat (2/3 width on large screens) */}
          <div className="lg:col-span-2 bg-white border border-slate-200 rounded-2xl shadow-sm flex flex-col">
            <div
              ref={logRef}
              className="h-[520px] overflow-y-auto p-4 space-y-4"
            >
              {msgs.map((m, i) => (
                <div
                  key={i}
                  className={
                    m.role === "user"
                      ? "text-blue-700"
                      : "text-emerald-700"
                  }
                >
                  <div className="text-sm font-semibold mb-1">
                    {m.role === "user" ? "You" : "Companion"}
                  </div>
                  <pre className="whitespace-pre-wrap break-words text-slate-800">
                    {m.content}
                  </pre>
                </div>
              ))}
              {loading && (
                <div className="text-emerald-700 animate-pulse">
                  Companion is thinking…
                </div>
              )}
              {msgs.length === 0 && !loading && (
                <div className="text-slate-500">
                  Say hi and tell me how you’re feeling today.
                </div>
              )}
            </div>

            <form onSubmit={onSend} className="border-t border-slate-200 p-3 flex gap-2">
              <input
                className="flex-1 rounded-xl border border-slate-300 px-4 py-3 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                placeholder="Tell me how you feel…"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) onSend(e);
                }}
                disabled={loading}
              />
              <button
                type="submit"
                disabled={loading || !input.trim()}
                className="rounded-xl bg-emerald-600 text-white px-5 py-3 font-medium hover:bg-emerald-700 disabled:opacity-50"
              >
                Send
              </button>
            </form>
          </div>

          {/* Insights side panel */}
          <div>
            <Insights latest={latest} />
          </div>
        </div>

        <div className="text-xs text-slate-500 mt-4">
          API via Vite proxy: <code>/api</code> → <code>http://127.0.0.1:8000</code> &nbsp;·&nbsp; user:&nbsp;
          <code className="select-all">{userId}</code>
        </div>
      </div>
    </div>
  );
}
