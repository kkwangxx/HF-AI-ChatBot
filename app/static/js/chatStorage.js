/**
 * 聊天会话本地存储抽象。
 * 当前：localStorage；未来可替换为后端 API。
 */
(function (global) {
  "use strict";

  const STORAGE_KEY = "chat_bot_conversations_v1";
  const THEME_KEY = "chat_bot_theme_v1";
  const MODEL_KEY = "chat_bot_model_v1";

  function uid() {
    return `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`;
  }

  function now() {
    return Date.now();
  }

  function createConversation(title) {
    const ts = now();
    return {
      id: uid(),
      title: title || "新对话",
      messages: [],
      createdAt: ts,
      updatedAt: ts,
    };
  }

  function createMessage(role, content, status, attachments) {
    const msg = {
      id: uid(),
      role,
      content: content || "",
      status: status || "completed",
    };
    if (attachments && attachments.length) {
      msg.attachments = attachments;
    }
    return msg;
  }

  function loadAll() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) {
        return { conversations: [], activeId: null };
      }
      const data = JSON.parse(raw);
      if (!data || !Array.isArray(data.conversations)) {
        return { conversations: [], activeId: null };
      }
      return {
        conversations: data.conversations,
        activeId: data.activeId || null,
      };
    } catch (err) {
      console.error("读取 localStorage 失败", err);
      return { conversations: [], activeId: null };
    }
  }

  function saveAll(conversations, activeId) {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        conversations,
        activeId,
        savedAt: now(),
      }),
    );
  }

  function getTheme() {
    return localStorage.getItem(THEME_KEY) || "system";
  }

  function setTheme(theme) {
    localStorage.setItem(THEME_KEY, theme);
  }

  function getSelectedModel() {
    return localStorage.getItem(MODEL_KEY) || "";
  }

  function setSelectedModel(model) {
    if (model) {
      localStorage.setItem(MODEL_KEY, model);
    } else {
      localStorage.removeItem(MODEL_KEY);
    }
  }

  global.ChatStorage = {
    uid,
    createConversation,
    createMessage,
    loadAll,
    saveAll,
    getTheme,
    setTheme,
    getSelectedModel,
    setSelectedModel,
  };
})(window);
