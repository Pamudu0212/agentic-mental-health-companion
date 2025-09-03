import { useEffect, useRef, useState } from "react";
import { sendChat } from "./api";

export default function App() {
  const [input, setInput] = useState("");
  const [msgs, setMsgs] = useState([]);
  const [loading, setLoading] = useState(false);
  const logRef = useRef(null);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [msgs, loading]);

  async function onSend(e) {
    e.preventDefault();
    const text = input.trim();
    if (!text) return;

    setMsgs(m => [...m, { role: "user", content: text }]);
    setInput("");
    setLoading(true);

    try {
      const res = await sendChat(text);
      const content =
        `Mood: ${res.mood}\n\n` +
        `Suggestion: ${res.strategy}\n\n` +
        `Note: ${res.encouragement}` +
        (res.crisis_detected ? `\n\n⚠️ Crisis detected.` : "");
      setMsgs(m => [...m, { role: "assistant", content }]);
    } catch (err) {
      setMsgs(m => [...m, { role: "assistant", content: `Error: ${err.message}` }]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="max-w-3xl mx-auto p-6">
        <h1 className="text-3xl font-bold mb-2">Agentic Mental Health Companion</h1>
        <p className="text-sm text-slate-600 mb-4">
          This app isn’t a medical service. If you’re in danger, contact local emergency services.
        </p>

        <div className="bg-white border border-slate-200 rounded-2xl shadow-sm">
          <div ref={logRef} className="h-[480px] overflow-y-auto p-4 space-y-4">
            {msgs.map((m, i) => (
              <div key={i} className={m.role === "user" ? "text-blue-700" : "text-emerald-700"}>
                <div className="text-sm font-semibold mb-1">
                  {m.role === "user" ? "You" : "Companion"}
                </div>
                <pre className="whitespace-pre-wrap text-slate-800">{m.content}</pre>
              </div>
            ))}
            {loading && <div className="text-emerald-700 animate-pulse">Thinking…</div>}
          </div>

          <form onSubmit={onSend} className="border-t border-slate-200 p-3 flex gap-2">
            <input
              className="flex-1 rounded-xl border border-slate-300 px-4 py-3 focus:outline-none focus:ring-2 focus:ring-emerald-500"
              placeholder="Tell me how you feel…"
              value={input}
              onChange={e => setInput(e.target.value)}
            />
            <button
              type="submit"
              disabled={loading}
              className="rounded-xl bg-emerald-600 text-white px-5 py-3 font-medium hover:bg-emerald-700 disabled:opacity-50"
            >
              Send
            </button>
          </form>
        </div>

        <div className="text-xs text-slate-500 mt-3">
          API: {import.meta.env.VITE_API_BASE}
        </div>
      </div>
    </div>
  );
}
