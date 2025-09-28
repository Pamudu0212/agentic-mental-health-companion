// src/App.jsx
import { useEffect, useMemo, useRef, useState } from "react";
import { sendChat, fetchResources } from "./api";
import CrisisCta from "./components/CrisisCta.tsx";
import MoodDial from "./components/MoodDial.jsx";

// ---------- utils ----------
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

// ---------- UI bits ----------
function Badge({ children, className = "" }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ${className}`}>
      {children}
    </span>
  );
}

function ResourceCard({ opt }) {
  const typeStyles = {
    video: "bg-rose-50 text-rose-700",
    article: "bg-indigo-50 text-indigo-700",
    book: "bg-amber-50 text-amber-800",
  };
  const t = (opt.type || "article").toLowerCase();
  return (
    <a
      href={opt.url}
      target="_blank"
      rel="noreferrer"
      className="block rounded-xl border border-slate-200 bg-white/90 p-3 hover:shadow transition"
    >
      <div className="flex items-start justify-between gap-2">
        <h4 className="text-sm font-semibold text-slate-800 leading-snug">{opt.title}</h4>
        <Badge className={typeStyles[t] || "bg-slate-100 text-slate-700"}>{opt.type}</Badge>
      </div>
      {opt.why && <p className="mt-1 text-[13px] text-slate-600">{opt.why}</p>}
      <div className="mt-2 flex items-center gap-2 text-[12px] text-slate-500">
        {opt.duration && <span>⏱ {opt.duration}</span>}
        {opt.source && <span>• {opt.source}</span>}
      </div>
    </a>
  );
}

function Insights({ latest, resources, loadingResources, needsClinician, crisisLink }) {
  const { mood, strategy, analyzing, safety } = latest || {};
  const level = safety?.level ?? "safe";

  const labelMap = {
    safe: "Safe",
    watch: "Watch",
    crisis_self: "Crisis (Self-harm)",
    crisis_others: "Crisis (Others)",
  };
  const chipClasses = {
    safe: "bg-emerald-50 text-emerald-700",
    watch: "bg-amber-50 text-amber-700",
    crisis_self: "bg-rose-100 text-rose-700",
    crisis_others: "bg-rose-100 text-rose-700",
  };

  return (
    <aside className="h-full">
      <div className="h-full rounded-3xl border border-emerald-100/60 bg-white/80 backdrop-blur-md shadow-md p-5 flex flex-col">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-800">Insights</h2>
          <span className={`px-2 py-1 text-xs rounded-full ${chipClasses[level]}`}>
            {labelMap[level] ?? "Safe"}
          </span>
        </div>

        {!!safety?.reason && (
          <p className="mt-2 text-xs text-slate-500">{safety.reason}</p>
        )}

        <div className="mt-4 space-y-5 overflow-auto pr-1">
          {/* Mood */}
          <section>
            <div className="text-[11px] uppercase tracking-wide text-slate-500">Mood</div>
            <div className="mt-1">
              {analyzing ? (
                <span className="inline-flex items-center gap-2 text-slate-700">
                  <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
                  Analyzing…
                </span>
              ) : mood ? (
                <div className="flex justify-center">
                  <MoodDial
                    mood={mood}
                    confidence={latest?.mood_confidence} // optional; safe if undefined
                    size={200}
                  />
                </div>
              ) : (
                <span className="text-slate-400">—</span>
              )}
            </div>
          </section>

          {/* Suggested step + WHY + source */}
          <section>
            <div className="text-[11px] uppercase tracking-wide text-slate-500">Suggested next step</div>
            {analyzing ? (
              <p className="mt-1 text-slate-700">Preparing a gentle suggestion…</p>
            ) : strategy ? (
              <div className="mt-1">
                {/* Step text (string for compat) */}
                <p className="text-slate-700 whitespace-pre-wrap break-words leading-relaxed">
                  {strategy}
                </p>

                {/* Why this helps (if backend provided it) */}
                {latest?.strategy_why && (
                  <p className="mt-2 text-[13px] text-slate-600">
                    <span className="font-medium text-slate-700">Why this helps: </span>
                    {latest.strategy_why}
                  </p>
                )}

                {/* View source button (if available) */}
                {latest?.advice_given && latest?.strategy_source?.url ? (
                  <a
                    href={latest.strategy_source.url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 mt-2 rounded-md border border-emerald-200 bg-emerald-50 px-2.5 py-1.5 text-[12px] font-medium text-emerald-700 hover:bg-emerald-100"
                  >
                    View source{latest.strategy_source.name ? ` · ${latest.strategy_source.name}` : ""}
                  </a>
                ) : null}
              </div>
            ) : (
              <p className="mt-1 text-slate-400">—</p>
            )}
          </section>

          {/* Helpful resources or crisis CTA */}
          <section>
            <div className="text-[11px] uppercase tracking-wide text-slate-500 mb-1">
              Helpful resources
            </div>

            {needsClinician && crisisLink ? (
              <div className="space-y-2">
                <p className="text-sm text-slate-700">
                  If you’re in immediate danger or feel unable to stay safe, please use the official support below.
                </p>
                <CrisisCta href={crisisLink} />
              </div>
            ) : loadingResources ? (
              <div className="text-sm text-slate-500">Finding options…</div>
            ) : resources?.length ? (
              <div className="grid grid-cols-1 gap-2">
                {resources.map((opt) => (
                  <ResourceCard key={opt.id} opt={opt} />
                ))}
              </div>
            ) : (
              <div className="text-sm text-slate-400">—</div>
            )}
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

// ---------- App ----------
export default function App() {
  const userId = useUserId();
  const [input, setInput] = useState("");
  const [msgs, setMsgs] = useState([]); // {role, content}
  const [loading, setLoading] = useState(false);
  const [latest, setLatest] = useState(null); // {mood, strategy, advice_given, strategy_source, strategy_why, safety, analyzing}
  const [resources, setResources] = useState([]); // [{id,type,title,url,...}]
  const [loadingResources, setLoadingResources] = useState(false);

  const [needsClinician, setNeedsClinician] = useState(false);
  const [crisisLink, setCrisisLink] = useState(null);

  const logRef = useRef(null);

  // ---- Chat-like scrolling ----
  const [autoStick, setAutoStick] = useState(true);
  const [showJump, setShowJump] = useState(false);

  const updateStickiness = () => {
    const el = logRef.current; // <-- fixed
    if (!el) return;
    const threshold = 80;
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

  useEffect(() => {
    if (autoStick) scrollToBottom("smooth");
  }, [msgs, loading]);

  async function onSend(e) {
    e.preventDefault();
    const text = input.trim();
    if (!text || loading) return;

    setMsgs((m) => [...m, { role: "user", content: text }]);
    setInput("");

    setLatest((prev) => ({ ...(prev || {}), analyzing: true }));
    setLoading(true);
    setLoadingResources(true);
    setResources([]);
    setNeedsClinician(false);
    setCrisisLink(null);

    try {
      // 1) Chat with backend (now includes strategy_why + strategy_source)
      const res = await sendChat(text, userId);
      setMsgs((m) => [...m, { role: "assistant", content: res.encouragement }]);

      const mood = res.mood || "neutral";
      const crisisDetected = !!res.crisis_detected;

      setLatest({
        mood,
        strategy: res.strategy || "",
        advice_given: !!res.advice_given,
        strategy_source: res.strategy_source || null,
        strategy_why: res.strategy_why || "",
        strategy_label: res.strategy_label || "",
        mood_confidence: res.mood_confidence, // safe if backend doesn't send it
        safety: res.safety ?? {
          level: crisisDetected ? "crisis_self" : "safe",
          reason: crisisDetected ? "Crisis mode" : "No crisis indicators found",
        },
        analyzing: false,
      });

      // 2) External resources / crisis link
      try {
        const r = await fetchResources({ user_text: text, mood, crisis: "none", history: null, exclude_ids: [] });
        setResources(r?.options || []);
        setNeedsClinician(!!r?.needs_clinician);
        setCrisisLink(r?.crisis_link ?? null);
      } catch {
        setResources([]);
        setNeedsClinician(false);
        setCrisisLink(null);
      } finally {
        setLoadingResources(false);
      }
    } catch (err) {
      const detail = err?.message || "Something went wrong. Please try again.";
      setMsgs((m) => [...m, { role: "assistant", content: `Error: ${detail}` }]);
      setLatest((prev) => (prev ? { ...prev, analyzing: false } : null));
      setLoadingResources(false);
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

        <div className="grid min-h-[calc(100vh-7.5rem)] grid-cols-1 gap-6 lg:grid-cols-3">
          {/* Chat */}
          <section className="relative lg:col-span-2 rounded-3xl border border-emerald-100/60 bg-white/80 backdrop-blur-md shadow-md flex flex-col">
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
                  <pre className="whitespace-pre-wrap break-words font-sans">{m.content}</pre>
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

            <form onSubmit={onSend} className="border-t border-emerald-100/70 px-4 sm:px-6 py-4 flex gap-3">
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

            <div className="text-[11px] text-slate-500 px-6 pb-3">
              API via Vite proxy: <code>/api</code> → <code>http://127.0.0.1:8000</code> · user:{" "}
              <code className="select-all">{userId}</code>
            </div>
          </section>

          {/* Insights / resources */}
          <section className="lg:col-span-1">
            <div className="h-full lg:sticky lg:top-[5.5rem]">
              <Insights
                latest={latest}
                resources={resources}
                loadingResources={loadingResources}
                needsClinician={needsClinician}
                crisisLink={crisisLink}
              />
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
