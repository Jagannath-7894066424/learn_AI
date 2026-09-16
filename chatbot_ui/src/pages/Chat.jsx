import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { askQuestion } from "../api.js";
import { useChatHistory } from "../ChatHistory.jsx";

const SUGGESTIONS = [
  "Summarise the main points",
  "What are the key numbers?",
  "List the important dates",
];

/** Copy an answer to the clipboard, with a moment of confirmation. */
function CopyButton({ text }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      return; // clipboard blocked (insecure origin / denied) — fail quietly
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 1600);
  }

  return (
    <div className="answer-actions">
      <button
        className={`copy-button ${copied ? "copied" : ""}`}
        onClick={copy}
        aria-label={copied ? "Copied" : "Copy answer"}
        title={copied ? "Copied" : "Copy"}
      >
        {copied ? (
          <svg viewBox="0 0 24 24" fill="none" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <path d="m20 6-11 11-5-5" />
          </svg>
        ) : (
          <svg viewBox="0 0 24 24" fill="none" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <rect x="9" y="9" width="12" height="12" rx="2" />
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
          </svg>
        )}
      </button>
    </div>
  );
}

/** Model answers are markdown — render them properly instead of showing raw **. */
function Answer({ text }) {
  return (
    <div className="markdown">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
    </div>
  );
}

/** The input box — centred on an empty chat, pinned to the bottom once talking. */
function Composer({ value, onChange, onSubmit, busy, inputRef }) {
  return (
    <form
      className="composer"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit(value);
      }}
    >
      <input
        ref={inputRef}
        type="text"
        value={value}
        placeholder="Ask anything about your documents…"
        onChange={(e) => onChange(e.target.value)}
        disabled={busy}
        autoFocus
      />
      <button type="submit" disabled={busy || !value.trim()} aria-label="Send">
        {busy ? <span className="spinner small" /> : "↑"}
      </button>
    </form>
  );
}

export default function Chat() {
  const { messages, addMessage } = useChatHistory();
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const endRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  async function send(text) {
    const trimmed = text.trim();
    if (!trimmed || busy) return;

    addMessage({ role: "user", text: trimmed }, { titleIfFirst: trimmed });
    setQuestion("");
    setBusy(true);

    try {
      const result = await askQuestion(trimmed);
      addMessage({ role: "bot", text: result.answer, sources: result.sources });
    } catch (err) {
      addMessage({ role: "error", text: err.message });
    } finally {
      setBusy(false);
      inputRef.current?.focus();
    }
  }

  // ---- empty state: big centred prompt, like a fresh workspace ----
  if (messages.length === 0 && !busy) {
    return (
      <div className="hero">
        <h2>What would you like to know?</h2>
        <p className="hero-sub">Answers come only from the documents you have uploaded.</p>

        <div className="hero-composer">
          <Composer
            value={question}
            onChange={setQuestion}
            onSubmit={send}
            busy={busy}
            inputRef={inputRef}
          />
        </div>

        <div className="suggestions">
          {SUGGESTIONS.map((s) => (
            <button key={s} type="button" onClick={() => send(s)}>
              {s}
            </button>
          ))}
        </div>
      </div>
    );
  }

  // ---- conversation ----
  return (
    <div className="chat">
      <div className="messages">
        {messages.map((message, index) => (
          <div key={index} className={`row ${message.role}`}>
            {message.role !== "user" && (
              <span className={`avatar ${message.role}`} aria-hidden="true">
                {message.role === "error" ? "!" : "AI"}
              </span>
            )}

            <div className="bubble">
              {message.role === "bot" && <CopyButton text={message.text} />}

              {message.role === "bot" ? <Answer text={message.text} /> : <p>{message.text}</p>}

              {message.sources?.length > 0 && (
                <details className="sources">
                  <summary>
                    Based on {message.sources.length} chunk
                    {message.sources.length === 1 ? "" : "s"}
                  </summary>
                  {message.sources.map((source, i) => (
                    <div key={i} className="source">
                      <div className="source-head">
                        <code>{source.source.split("/").pop()}</code>
                        <span className="match">
                          {Math.max(0, Math.round((1 - source.distance) * 100))}% match
                        </span>
                      </div>
                      <p>{source.snippet}…</p>
                    </div>
                  ))}
                </details>
              )}
            </div>
          </div>
        ))}

        {busy && (
          <div className="row bot">
            <span className="avatar bot" aria-hidden="true">AI</span>
            <div className="bubble typing"><span /><span /><span /></div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      <div className="composer-dock">
        <Composer
          value={question}
          onChange={setQuestion}
          onSubmit={send}
          busy={busy}
          inputRef={inputRef}
        />
        <p className="composer-note">Answers are grounded in your uploaded documents.</p>
      </div>
    </div>
  );
}
