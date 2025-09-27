// src/api.js

const BASE = "/api";

/**
 * Send a chat message to the backend.
 * Returns parsed JSON: { mood, strategy, encouragement, safety, crisis_detected, ... }.
 */
export async function sendChat(message, userId = "anon") {
  const payload = { user_text: message, user_id: userId };

  let res;
  try {
    res = await fetch(`${BASE}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      // same-origin cookies are sent by default; chat doesn’t need credentials
      body: JSON.stringify(payload),
    });
  } catch (err) {
    console.error("[sendChat] network error", err);
    throw new Error("Could not reach backend. Is it running on 127.0.0.1:8000?");
  }

  const text = await res.text();

  if (!res.ok) {
    // Try to pull a cleaner message from backend JSON
    let detail = text;
    try {
      const j = JSON.parse(text);
      detail = j.message || j.error || detail;
    } catch {
      /* keep raw text */
    }
    console.error("[sendChat] HTTP", res.status, detail);
    throw new Error(detail || `Request failed: ${res.status}`);
  }

  try {
    return JSON.parse(text);
  } catch {
    console.error("[sendChat] non-JSON response:", text);
    throw new Error("Backend returned a non-JSON response");
  }
}

/** Fetch currently logged-in user (from session). Always resolves quickly. */
export async function fetchMe() {
  try {
    const r = await fetch(`${BASE}/auth/me`, { credentials: "include" });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return await r.json(); // {} when logged out
  } catch (e) {
    console.warn("[fetchMe] failed:", e);
    return {}; // keep UI unblocked
  }
}

/** Start Google OAuth login (backend will redirect to Google). */
export function loginWithGoogle() {
  window.location.href = `${BASE}/auth/google`;
}

/** End session on backend (clears server-side cookie). */
export async function logout() {
  try {
    await fetch(`${BASE}/auth/logout`, {
      method: "POST",
      credentials: "include",
    });
  } catch (e) {
    console.warn("[logout] failed:", e);
  }
}

/** Micro-step suggestion */
export async function fetchStrategy({ user_text, mood = "neutral", crisis = "none", history = null }) {
  const r = await fetch(`${BASE}/suggest/strategy`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_text, mood, crisis, history }),
  });
  if (!r.ok) throw new Error(`Strategy failed: ${r.status} ${await r.text()}`);
  return r.json(); // { strategy: "..." }
}

/** External resource options (video/article/book or crisis link) */
export async function fetchResources({ user_text, mood = "neutral", crisis = "none", history = null, exclude_ids = [] }) {
  const r = await fetch(`${BASE}/suggest/resources`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_text, mood, crisis, history, exclude_ids }),
  });
  if (!r.ok) throw new Error(`Resources failed: ${r.status} ${await r.text()}`);
  return r.json();
  /* Response shape:
    {
      options: [
        { id, type, title, url, duration?, why?, cautions?, source? }
      ],
      needs_clinician: boolean,
      crisis_link?: string   // present only when crisis detected
    }
  */
}
