// src/api.js

// Session management
let sessionId = localStorage.getItem('chat_session_id');
if (!sessionId) {
    sessionId = 'session_' + Math.random().toString(36).substr(2, 9);
    localStorage.setItem('chat_session_id', sessionId);
}

// Chat with the main pipeline
export async function sendChat(message, userId = "anon") {
  const r = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
        user_text: message,
        user_id: userId,
        session_id: sessionId // Add session_id
    }),
  });
  if (!r.ok) throw new Error(`Request failed: ${r.status} ${await r.text()}`);
  return r.json(); // { reply: "...", ... }
}

// Micro-step suggestion
export async function fetchStrategy({ user_text, mood = "neutral", crisis = "none", history = null }) {
  const r = await fetch("/api/suggest/strategy", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
        user_text,
        mood,
        crisis,
        history,
        session_id: sessionId // Add session_id
    }),
  });
  if (!r.ok) throw new Error(`Strategy failed: ${r.status} ${await r.text()}`);
  return r.json(); // { strategy: "..." }
}

// External resource options (video/article/book or crisis link)
export async function fetchResources({
  user_text,
  mood = "neutral",
  crisis = "none",
  history = null,
  exclude_ids = [],
}) {
  const r = await fetch("/api/suggest/resources", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
        user_text,
        mood,
        crisis,
        history,
        exclude_ids,
        session_id: sessionId // Add session_id
    }),
  });
  if (!r.ok) throw new Error(`Resources failed: ${r.status} ${await r.text()}`);
  return r.json();
  /*
    Response shape:
    {
      options: [
        { id, type, title, url, duration?, why?, cautions?, source? }
      ],
      needs_clinician: boolean,
      crisis_link?: string   // <-- present only when crisis detected
    }
  */
}

// Start a new conversation session
export function startNewSession() {
    const newSessionId = 'session_' + Math.random().toString(36).substr(2, 9);
    localStorage.setItem('chat_session_id', newSessionId);
    sessionId = newSessionId;
    return newSessionId;
}

// Get current session ID
export function getCurrentSessionId() {
    return sessionId;
}