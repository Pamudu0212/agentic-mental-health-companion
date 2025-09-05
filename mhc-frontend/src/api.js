// src/api.js
export async function sendChat(message, userId="anon"){
  const r = await fetch('/api/chat', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ user_text: message, user_id: userId }),
  });
  if (!r.ok) throw new Error(`Request failed: ${r.status} ${await r.text()}`);
  return r.json();
}
