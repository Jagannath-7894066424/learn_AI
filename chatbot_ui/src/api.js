// Thin wrapper around the backend API. Vite proxies /api to localhost:8000.

async function handle(response) {
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      const detail = body.detail;
      message = typeof detail === "string" ? detail : detail?.message ?? message;
    } catch {
      /* response had no JSON body — keep the generic message */
    }
    throw new Error(message);
  }
  return response.json();
}

export const getHealth = () => fetch("/api/health").then(handle);

export const getDocuments = () => fetch("/api/documents").then(handle);

export function uploadDocuments(files) {
  const form = new FormData();
  for (const file of files) form.append("files", file);
  return fetch("/api/documents/upload", { method: "POST", body: form }).then(handle);
}

export const deleteDocument = (source) =>
  fetch(`/api/documents?source=${encodeURIComponent(source)}`, { method: "DELETE" }).then(handle);

export const askQuestion = (question) =>
  fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  }).then(handle);
