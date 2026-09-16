import { useCallback, useEffect, useRef, useState } from "react";
import { deleteDocument, getDocuments, uploadDocuments } from "../api.js";

const TYPES = [".txt", ".md", ".pdf", ".xlsx", ".csv"];

/** Colour + label for a file, based on its extension. */
function fileKind(source) {
  const ext = source.slice(source.lastIndexOf(".")).toLowerCase();
  const map = {
    ".pdf": ["PDF", "kind-pdf"],
    ".xlsx": ["XLS", "kind-sheet"],
    ".xlsm": ["XLS", "kind-sheet"],
    ".csv": ["CSV", "kind-sheet"],
    ".md": ["MD", "kind-doc"],
    ".txt": ["TXT", "kind-doc"],
  };
  return map[ext] ?? ["FILE", "kind-doc"];
}

export default function Uploader({ onChange }) {
  const [documents, setDocuments] = useState([]);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(null); // { type, text }
  const inputRef = useRef(null);

  const refresh = useCallback(
    () =>
      getDocuments()
        .then((data) => setDocuments(data.documents))
        .catch((err) => setMessage({ type: "error", text: err.message })),
    []
  );

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function handleFiles(fileList) {
    const files = Array.from(fileList ?? []);
    if (files.length === 0) return;

    setBusy(true);
    setMessage(null);
    try {
      const result = await uploadDocuments(files);
      const chunks = result.ingested.reduce((sum, item) => sum + item.chunks, 0);
      const parts = [];
      if (result.ingested.length) {
        parts.push(`Indexed ${result.ingested.length} file(s) into ${chunks} chunks.`);
      }
      if (result.skipped?.length) {
        parts.push(
          "Skipped " + result.skipped.map((s) => `${s.filename} (${s.reason})`).join("; ") + "."
        );
      }
      setMessage({ type: result.ingested.length ? "ok" : "error", text: parts.join(" ") });
      await refresh();
      onChange?.();
    } catch (err) {
      setMessage({ type: "error", text: err.message });
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = ""; // allow re-uploading the same file
    }
  }

  async function handleDelete(source) {
    try {
      await deleteDocument(source);
      await refresh();
      onChange?.();
      setMessage({ type: "ok", text: `Removed ${source} from the index.` });
    } catch (err) {
      setMessage({ type: "error", text: err.message });
    }
  }

  function onDrop(event) {
    event.preventDefault();
    setDragging(false);
    handleFiles(event.dataTransfer.files);
  }

  const totalChunks = documents.reduce((sum, d) => sum + d.chunks, 0);

  return (
    <section className="page">
      <header className="page-head">
        <h2>Upload documents</h2>
        <p>
          Text is extracted, split into ~800 character chunks, embedded on your machine, and stored
          in Postgres. Re-uploading a file replaces its existing chunks.
        </p>
      </header>

      <div
        className={`dropzone ${dragging ? "dragging" : ""} ${busy ? "busy" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => !busy && inputRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && !busy && inputRef.current?.click()}
      >
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".txt,.md,.pdf,.xlsx,.xlsm,.csv"
          hidden
          onChange={(e) => handleFiles(e.target.files)}
        />

        {busy ? (
          <>
            <span className="spinner" />
            <p className="dropzone-title">Embedding…</p>
            <p className="dropzone-hint">First run downloads the model — this takes a moment.</p>
          </>
        ) : (
          <>
            <span className="dropzone-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <path d="m7 10 5-5 5 5" />
                <path d="M12 5v12" />
              </svg>
            </span>
            <p className="dropzone-title">Drop files here</p>
            <p className="dropzone-hint">or click to browse</p>
            <div className="type-chips">
              {TYPES.map((t) => (
                <span key={t} className="type-chip">{t}</span>
              ))}
            </div>
          </>
        )}
      </div>

      {message && (
        <div className={`message ${message.type}`} role="status">
          {message.text}
        </div>
      )}

      <div className="list-head">
        <h3>Indexed documents</h3>
        {documents.length > 0 && (
          <span className="count-pill">
            {documents.length} files · {totalChunks} chunks
          </span>
        )}
      </div>

      {documents.length === 0 ? (
        <div className="empty-card">
          <p>Nothing indexed yet.</p>
          <span>Upload a file above to start asking questions.</span>
        </div>
      ) : (
        <ul className="doclist">
          {documents.map((doc) => {
            const [label, kindClass] = fileKind(doc.source);
            const name = doc.source.split("/").pop();
            const folder = doc.source.slice(0, doc.source.length - name.length);
            return (
              <li key={doc.source}>
                <span className={`kind ${kindClass}`}>{label}</span>
                <span className="doc-name">
                  <strong>{name}</strong>
                  {folder && <em>{folder}</em>}
                </span>
                <span className="doc-chunks">{doc.chunks} chunks</span>
                <button
                  className="remove-button"
                  onClick={() => handleDelete(doc.source)}
                  aria-label={`Remove ${name}`}
                >
                  Remove
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
