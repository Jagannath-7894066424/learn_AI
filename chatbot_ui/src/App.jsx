import { useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import Uploader from "./pages/Uploader.jsx";
import Chat from "./pages/Chat.jsx";
import { getHealth } from "./api.js";
import { ChatHistoryProvider, useChatHistory } from "./ChatHistory.jsx";
import { relativeTime } from "./history.js";

/* ----------------------------- small icons ----------------------------- */
const Icon = {
  logo: (
    <svg viewBox="0 0 24 24" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 3v10" /><path d="m8 7 4-4 4 4" />
      <path d="M4 14v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4" />
    </svg>
  ),
  pencil: (
    <svg viewBox="0 0 24 24" fill="none" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" />
    </svg>
  ),
  chat: (
    <svg viewBox="0 0 24 24" fill="none" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
  ),
  upload: (
    <svg viewBox="0 0 24 24" fill="none" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <path d="m7 10 5-5 5 5" /><path d="M12 5v12" />
    </svg>
  ),
  panel: (
    <svg viewBox="0 0 24 24" fill="none" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="18" height="18" rx="2" /><path d="M9 3v18" />
    </svg>
  ),
};

/* ------------------------------- sidebar ------------------------------- */
function Sidebar({ health, error, collapsed, onToggle }) {
  const { conversations, activeId, selectChat, startNewChat, deleteChat } = useChatHistory();
  const navigate = useNavigate();

  function handleNewChat() {
    startNewChat();
    navigate("/chat");
  }

  return (
    <aside className={`sidebar ${collapsed ? "collapsed" : ""}`}>
      <div className="sidebar-top">
        <span className="brand">
          <span className="logo" aria-hidden="true">{Icon.logo}</span>
          <span className="brand-name">Upload &amp; Ask</span>
        </span>
        <button className="icon-button" onClick={onToggle} aria-label="Collapse sidebar" title="Collapse">
          {Icon.panel}
        </button>
      </div>

      <nav className="side-nav">
        <button className="side-item primary" onClick={handleNewChat}>
          <span className="side-icon">{Icon.pencil}</span>
          <span>New chat</span>
        </button>
        <NavLink to="/chat" className={({ isActive }) => `side-item ${isActive ? "active" : ""}`}>
          <span className="side-icon">{Icon.chat}</span>
          <span>Chat</span>
        </NavLink>
        <NavLink to="/upload" className={({ isActive }) => `side-item ${isActive ? "active" : ""}`}>
          <span className="side-icon">{Icon.upload}</span>
          <span>Upload</span>
          {health?.documents > 0 && <span className="side-badge">{health.documents}</span>}
        </NavLink>
      </nav>

      <p className="side-label">Recents</p>

      <ul className="recents">
        {conversations.length === 0 && <li className="recents-empty">No conversations yet</li>}
        {conversations.map((c) => (
          <li
            key={c.id}
            className={c.id === activeId ? "active" : ""}
            onClick={() => {
              selectChat(c.id);
              navigate("/chat");
            }}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                selectChat(c.id);
                navigate("/chat");
              }
            }}
            title={c.title}
          >
            <span className="recent-title">{c.title}</span>
            <span className="recent-time">{relativeTime(c.updatedAt)}</span>
            <button
              className="recent-delete"
              onClick={(e) => {
                e.stopPropagation();
                deleteChat(c.id);
              }}
              aria-label={`Delete ${c.title}`}
              title="Delete"
            >
              ×
            </button>
          </li>
        ))}
      </ul>

      <div className="sidebar-foot">
        {error ? (
          <span className="foot-status error">
            <i className="dot" /> Backend offline
          </span>
        ) : health ? (
          <>
            <span className={`foot-status ${health.llm_ready ? "ok" : "warn"}`}>
              <i className="dot" /> {health.provider} · {health.model}
            </span>
            <span className="foot-meta">
              {health.documents} docs · {health.chunks} chunks
            </span>
          </>
        ) : (
          <span className="foot-status">connecting…</span>
        )}
      </div>
    </aside>
  );
}

/* --------------------------------- shell -------------------------------- */
function Shell() {
  const [health, setHealth] = useState(null);
  const [error, setError] = useState("");
  // Start collapsed on narrow screens, where the sidebar is an overlay.
  const [collapsed, setCollapsed] = useState(
    () => typeof window !== "undefined" && window.innerWidth <= 860
  );

  const refreshHealth = () =>
    getHealth()
      .then((data) => {
        setHealth(data);
        setError("");
      })
      .catch((err) => setError(err.message));

  useEffect(() => {
    refreshHealth();
    const timer = setInterval(refreshHealth, 5000);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className={`shell ${collapsed ? "collapsed" : ""}`}>
      <Sidebar
        health={health}
        error={error}
        collapsed={collapsed}
        onToggle={() => setCollapsed((v) => !v)}
      />

      <div className="content">
        <header className="topbar">
          {collapsed && (
            <button
              className="icon-button floating"
              onClick={() => setCollapsed(false)}
              aria-label="Show sidebar"
            >
              {Icon.panel}
            </button>
          )}

          <div className="segmented" role="tablist">
            <NavLink to="/chat" className={({ isActive }) => (isActive ? "active" : "")}>
              Chat
            </NavLink>
            <NavLink to="/upload" className={({ isActive }) => (isActive ? "active" : "")}>
              Upload
            </NavLink>
          </div>
        </header>

        {health && !health.llm_ready && (
          <div className="banner">
            <strong>No API key configured for {health.provider}.</strong> Uploading and search work,
            but answering will fail until you set <code>GROQ_API_KEY</code> in{" "}
            <code>chatbot_be/.env</code> and restart the backend.
          </div>
        )}

        {health?.status === "degraded" && health?.error && (
          <div className="banner banner-error">
            <strong>Database unreachable.</strong> {health.error}
          </div>
        )}

        <main className="main">
          <Routes>
            <Route path="/" element={<Navigate to="/chat" replace />} />
            <Route path="/upload" element={<Uploader onChange={refreshHealth} />} />
            <Route path="/chat" element={<Chat />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <ChatHistoryProvider>
      <Shell />
    </ChatHistoryProvider>
  );
}
