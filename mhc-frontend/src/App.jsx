// src/App.jsx
import { useEffect, useMemo, useRef, useState } from "react";
import { sendChat } from "./api";

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
  const { mood, strategy, crisis_detected, analyzing } = latest || {};
  return (
    <aside className="h-full">
      <div className="h-full rounded-3xl border border-emerald-100/60 bg-white/80 backdrop-blur-md shadow-md p-5 flex flex-col">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-800">Insights</h2>
          {crisis_detected ? (
            <span className="px-2 py-1 text-xs rounded-full bg-rose-100 text-rose-700">
              Crisis detected
            </span>
          ) : (
            <span className="px-2 py-1 text-xs rounded-full bg-emerald-50 text-emerald-700">
              Safe
            </span>
          )}
        </div>

        <div className="mt-4 space-y-4 overflow-auto pr-1">
          <section>
            <div className="text-[11px] uppercase tracking-wide text-slate-500">
              Mood
            </div>
            <div className="mt-1 text-base font-medium text-slate-800">
              {analyzing ? (
                <span className="inline-flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
                  Analyzing…
                </span>
              ) : mood || "—"}
            </div>
          </section>

          <section>
            <div className="text-[11px] uppercase tracking-wide text-slate-500">
              Suggested next step
            </div>
            <p className="mt-1 text-slate-700 whitespace-pre-wrap break-words leading-relaxed">
              {analyzing ? "Preparing a gentle suggestion…" : strategy || "—"}
            </p>
          </section>

        <p className="text-xs text-slate-500 mt-auto pt-2">
            These insights are assistive, not clinical guidance.
          </p>
        </div>
      </div>
    </aside>
  );
}

function Bubble({ role, children }) {
  const isUser = role === "user";
  return (
    <div className={`flex items-start gap-3 ${isUser ? "justify-end" : ""}`}>
      {!isUser && (
        <div className="h-9 w-9 shrink-0 rounded-full bg-emerald-100 flex items-center justify-center text-emerald-700 shadow">
          🤝
        </div>
      )}
      <div
        className={[
          "max-w-[78%] rounded-2xl px-4 py-3 shadow-sm leading-relaxed",
          isUser
            ? "bg-sky-100 text-sky-900 rounded-br-md border border-sky-200"
            : "bg-white/90 text-slate-800 border border-emerald-100 rounded-bl-md",
        ].join(" ")}
      >
        {children}
      </div>
      {isUser && (
        <div className="h-9 w-9 shrink-0 rounded-full bg-sky-100 flex items-center justify-center text-sky-700 shadow">
          😊
        </div>
      )}
    </div>
  );
}

export default function App() {
  const userId = useUserId();
  const [input, setInput] = useState("");
  const [msgs, setMsgs] = useState([]); // {role, content}
  const [loading, setLoading] = useState(false);
  const [latest, setLatest] = useState(null); // {mood, strategy, crisis_detected, analyzing}
  const logRef = useRef(null);

  // ---- ChatGPT-like scrolling ----
  const [autoStick, setAutoStick] = useState(true); // stick to bottom unless user scrolls up
  const [showJump, setShowJump] = useState(false);

  // Decide if we're near bottom
  const updateStickiness = () => {
    const el = logRef.current;
    if (!el) return;
    const threshold = 80; // px from bottom considered "at bottom"
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < threshold;
    setShowJump(!atBottom);
    if (atBottom) setAutoStick(true);
  };

  useEffect(() => {
    const el = logRef.current;
    if (!el) return;
    el.addEventListener("scroll", updateStickiness, { passive: true });
    return () => el.removeEventListener("scroll", updateStickiness);
  }, []);

  const scrollToBottom = (behavior = "smooth") => {
    const el = logRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior });
  };

  // Auto-scroll only if user hasn't scrolled up
  useEffect(() => {
    if (autoStick) scrollToBottom("smooth");
  }, [msgs, loading]);

  async function onSend(e) {
    e.preventDefault();
    const text = input.trim();
    if (!text || loading) return;

    // Append user message
    setMsgs((m) => [...m, { role: "user", content: text }]);
    setInput("");

    // Optimistic: Insights show "Analyzing…"
    setLatest((prev) => ({
      ...(prev || { crisis_detected: false }),
      analyzing: true,
    }));

    setLoading(true);
    try {
      const res = await sendChat(text, userId);

      // Append assistant message
      setMsgs((m) => [...m, { role: "assistant", content: res.encouragement }]);

      // Finalize Insights
      setLatest({
        mood: res.mood,
        strategy: res.strategy,
        crisis_detected: res.crisis_detected,
        analyzing: false,
      });
    } catch (err) {
      const detail = err?.message || "Something went wrong. Please try again.";
      setMsgs((m) => [...m, { role: "assistant", content: `Error: ${detail}` }]);

      // Clear analyzing state, keep previous insights
      setLatest((prev) => (prev ? { ...prev, analyzing: false } : null));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen w-full overflow-x-hidden bg-gradient-to-br from-emerald-50 via-teal-50 to-sky-50">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 py-6">
        <header className="mb-4">
          <h1 className="text-2xl md:text-3xl font-bold tracking-tight text-slate-800">
            Agentic Mental Health Companion
          </h1>
          <p className="text-sm text-slate-600 mt-1">
            This isn’t a medical service. If you’re in danger, contact local emergency services.
          </p>
        </header>

        {/* NOTE: min-h instead of fixed h so the page can extend & scroll */}
        <div className="grid min-h-[calc(100vh-7.5rem)] grid-cols-1 gap-6 lg:grid-cols-3">
          {/* Chat */}
          <section className="relative lg:col-span-2 rounded-3xl border border-emerald-100/60 bg-white/80 backdrop-blur-md shadow-md flex flex-col">
            {/* messages */}
            <div
              ref={logRef}
              className="flex-1 overflow-y-auto px-4 sm:px-6 py-5 space-y-4"
              onWheel={() => setAutoStick(false)}
              onTouchMove={() => setAutoStick(false)}
            >
              {msgs.length === 0 && !loading && (
                <div className="mx-auto max-w-prose text-center text-slate-600">
                  Welcome. Take a breath. When you’re ready, share how you’re feeling today.
                </div>
              )}
              {msgs.map((m, i) => (
                <Bubble key={i} role={m.role}>
                  <pre className="whitespace-pre-wrap break-words font-sans">
                    {m.content}
                  </pre>
                </Bubble>
              ))}
              {loading && (
                <div className="flex items-center gap-2 text-emerald-700">
                  <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
                  <span className="h-2 w-2 rounded-full bg-emerald-300 animate-pulse [animation-delay:150ms]" />
                  <span className="h-2 w-2 rounded-full bg-emerald-200 animate-pulse [animation-delay:300ms]" />
                  <span className="ml-2">Thinking…</span>
                </div>
              )}
            </div>

            {/* input */}
            <form
              onSubmit={onSend}
              className="border-t border-emerald-100/70 px-4 sm:px-6 py-4 flex gap-3"
            >
              <input
                className="flex-1 rounded-2xl border border-slate-200 bg-white/90 px-4 py-3 shadow-inner placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-400"
                placeholder="Tell me how you feel…"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) onSend(e);
                }}
                disabled={loading}
                onFocus={() => setAutoStick(true)}
              />
              <button
                type="submit"
                disabled={loading || !input.trim()}
                className="rounded-2xl bg-emerald-600 text-white px-5 py-3 font-medium shadow-sm hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Send
              </button>
            </form>

            {/* Jump to latest */}
            {showJump && (
              <button
                onClick={() => {
                  setAutoStick(true);
                  scrollToBottom("smooth");
                }}
                className="absolute left-1/2 -translate-x-1/2 bottom-20 rounded-full bg-white/90 border border-emerald-200 px-3 py-1 text-sm shadow hover:bg-white"
                aria-label="Jump to latest"
              >
                Jump to latest ↓
              </button>
            )}

            <div className="text-[11px] text-slate-500 px-6 pb-3">
              API via Vite proxy: <code>/api</code> → <code>http://127.0.0.1:8000</code> · user:{" "}
              <code className="select-all">{userId}</code>
            </div>
          </section>

          {/* Insights */}
          <section className="lg:col-span-1">
            {/* sticky keeps it visible while the page scrolls */}
            <div className="h-full lg:sticky lg:top-[5.5rem]">
              <Insights latest={latest} />
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
