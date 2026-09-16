// Conversation state, shared between the app-wide sidebar and the chat page.
//
// Storage is still the browser only (see history.js). Lifting it into context
// lets the sidebar list conversations while the chat page reads and writes the
// active one, without either owning the other's state.

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { loadConversations, newConversation, saveConversations, titleFrom } from "./history.js";

const ChatHistoryContext = createContext(null);

export function ChatHistoryProvider({ children }) {
  // Read storage exactly once so both pieces of state agree — initialising them
  // separately would create two different conversations on a cold start.
  const [initial] = useState(() => {
    const saved = loadConversations();
    return saved.length ? saved : [newConversation()];
  });
  const [conversations, setConversations] = useState(initial);
  const [activeId, setActiveId] = useState(initial[0].id);

  useEffect(() => {
    saveConversations(conversations);
  }, [conversations]);

  const value = useMemo(() => {
    const active = conversations.find((c) => c.id === activeId) ?? conversations[0];

    /** Replace the active conversation with an updated copy. */
    function updateActive(updater) {
      setConversations((prev) =>
        prev.map((c) => (c.id === activeId ? { ...updater(c), updatedAt: Date.now() } : c))
      );
    }

    function startNewChat() {
      // Reuse the current one if it is still untouched, so the list doesn't
      // fill up with empty "New chat" rows.
      const current = conversations.find((c) => c.id === activeId);
      if (current && current.messages.length === 0) return current.id;

      const fresh = newConversation();
      setConversations((prev) => [fresh, ...prev]);
      setActiveId(fresh.id);
      return fresh.id;
    }

    function deleteChat(id) {
      // Computed outside the updater: setState updaters must stay side-effect
      // free (StrictMode runs them twice).
      const remaining = conversations.filter((c) => c.id !== id);
      const next = remaining.length ? remaining : [newConversation()];
      setConversations(next);
      if (id === activeId) setActiveId(next[0].id);
    }

    function addMessage(message, { titleIfFirst } = {}) {
      updateActive((c) => ({
        ...c,
        title: c.messages.length === 0 && titleIfFirst ? titleFrom(titleIfFirst) : c.title,
        messages: [...c.messages, message],
      }));
    }

    return {
      conversations,
      activeId,
      active,
      messages: active?.messages ?? [],
      selectChat: setActiveId,
      startNewChat,
      deleteChat,
      addMessage,
    };
  }, [conversations, activeId]);

  return <ChatHistoryContext.Provider value={value}>{children}</ChatHistoryContext.Provider>;
}

export function useChatHistory() {
  const context = useContext(ChatHistoryContext);
  if (!context) throw new Error("useChatHistory must be used inside <ChatHistoryProvider>");
  return context;
}
