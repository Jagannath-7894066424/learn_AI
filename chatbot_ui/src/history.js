// Chat history, stored in the browser only (localStorage).
//
// Kept client-side for now: it survives refreshes and is private to this
// browser, but is not shared across devices. Moving it to Postgres later
// means swapping these four functions for API calls — nothing else changes.

const KEY = "upload-and-ask:conversations";
const MAX = 50; // keep the list manageable

/** Read every saved conversation, newest first. Never throws. */
export function loadConversations() {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.sort((a, b) => (b.updatedAt ?? 0) - (a.updatedAt ?? 0));
  } catch {
    // Private mode, cleared storage, or corrupt JSON — start empty.
    return [];
  }
}

/** Persist the list. Never throws (storage can be full or blocked). */
export function saveConversations(conversations) {
  try {
    localStorage.setItem(KEY, JSON.stringify(conversations.slice(0, MAX)));
  } catch {
    /* ignore — history is a convenience, not critical state */
  }
}

export function newConversation() {
  return {
    id: `c_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
    title: "New chat",
    messages: [],
    createdAt: Date.now(),
    updatedAt: Date.now(),
  };
}

/** First question becomes the title, trimmed to something list-sized. */
export function titleFrom(text) {
  const clean = text.trim().replace(/\s+/g, " ");
  return clean.length > 42 ? `${clean.slice(0, 42)}…` : clean || "New chat";
}

/** "just now" / "3h ago" / "12 Mar" for the sidebar. */
export function relativeTime(timestamp) {
  const seconds = Math.floor((Date.now() - timestamp) / 1000);
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  if (seconds < 604800) return `${Math.floor(seconds / 86400)}d ago`;
  return new Date(timestamp).toLocaleDateString(undefined, { day: "numeric", month: "short" });
}
