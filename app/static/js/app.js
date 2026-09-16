/**
 * 聊天页面主逻辑（基于 One-Chat 交互改造）。
 */
(function () {
  "use strict";

  const $ = (sel) => document.querySelector(sel);
  const CHAT_URL = "/api/chat";
  const MODELS_URL = "/api/models";

  let conversations = [];
  let activeId = null;
  let abortController = null;
  let themeMode = "system";
  let availableModels = [];
  let selectedModel = "";
  let defaultModel = "";
  let pendingFiles = [];

  const MAX_FILES = 4;
  const MAX_IMAGE_BYTES = 4 * 1024 * 1024;
  const MAX_DOC_BYTES = 8 * 1024 * 1024;
  const MAX_TEXT_BYTES = 1 * 1024 * 1024;
  const IMAGE_TYPES = new Set(["image/jpeg", "image/png", "image/gif", "image/webp"]);
  const TEXT_EXT = new Set([
    "txt",
    "md",
    "json",
    "csv",
    "py",
    "js",
    "ts",
    "java",
    "sql",
    "xml",
    "yaml",
    "yml",
    "log",
  ]);

  function icon(id) {
    return `<svg class="icon"><use href="#${id}"></use></svg>`;
  }

  function toast(text) {
    const el = $("#toast");
    el.textContent = text;
    el.classList.add("show");
    setTimeout(() => el.classList.remove("show"), 2200);
  }

  function persist() {
    try {
      ChatStorage.saveAll(conversations, activeId);
    } catch (err) {
      console.error("保存失败", err);
      toast("本地存储空间不足，附件可能无法完整保存");
    }
  }

  function current() {
    return conversations.find((c) => c.id === activeId) || null;
  }

  function ensureActive() {
    if (!conversations.length) {
      const c = ChatStorage.createConversation("新对话");
      conversations.unshift(c);
      activeId = c.id;
      persist();
      return;
    }
    if (!activeId || !conversations.some((c) => c.id === activeId)) {
      activeId = conversations[0].id;
      persist();
    }
  }

  function applyTheme() {
    let theme = themeMode;
    if (theme === "system") {
      theme = window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light";
    }
    document.documentElement.dataset.theme = theme;
  }

  function cycleTheme() {
    themeMode =
      themeMode === "system" ? "dark" : themeMode === "dark" ? "light" : "system";
    ChatStorage.setTheme(themeMode);
    applyTheme();
    const labels = { system: "跟随系统", dark: "深色", light: "浅色" };
    toast(`主题：${labels[themeMode]}`);
  }

  function renderModelSelect() {
    const select = $("#modelSelect");
    if (!select) {
      return;
    }
    const models = availableModels.length ? availableModels : [defaultModel || "default"];
    if (!selectedModel || !models.includes(selectedModel)) {
      selectedModel = models.includes(defaultModel) ? defaultModel : models[0];
      ChatStorage.setSelectedModel(selectedModel);
    }
    select.innerHTML = models
      .map(
        (m) =>
          `<option value="${MarkdownRenderer.escapeHtml(m)}" ${
            m === selectedModel ? "selected" : ""
          }>${MarkdownRenderer.escapeHtml(m)}</option>`,
      )
      .join("");
  }

  async function loadModels() {
    try {
      const resp = await fetch(MODELS_URL);
      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}`);
      }
      const data = await resp.json();
      defaultModel = data.default || "";
      availableModels = Array.isArray(data.models) ? data.models : [];
      selectedModel = ChatStorage.getSelectedModel();
      renderModelSelect();
    } catch (err) {
      console.error("加载模型列表失败", err);
      defaultModel = $("#modelSelect")?.dataset?.fallback || "";
      availableModels = defaultModel ? [defaultModel] : [];
      selectedModel = ChatStorage.getSelectedModel() || defaultModel;
      renderModelSelect();
      toast("模型列表加载失败，已使用默认模型");
    }
  }

  function dayGroupLabel(ts) {
    const d = new Date(ts);
    const today = new Date();
    const startToday = new Date(today.getFullYear(), today.getMonth(), today.getDate());
    const startYesterday = new Date(startToday);
    startYesterday.setDate(startYesterday.getDate() - 1);
    if (d >= startToday) {
      return "今天";
    }
    if (d >= startYesterday) {
      return "昨天";
    }
    return "更早";
  }

  function renderChats() {
    const list = [...conversations].sort((a, b) => b.updatedAt - a.updatedAt);
    const groups = { 今天: [], 昨天: [], 更早: [] };
    list.forEach((c) => {
      groups[dayGroupLabel(c.updatedAt)].push(c);
    });

    const parts = [];
    ["今天", "昨天", "更早"].forEach((label) => {
      const items = groups[label];
      if (!items.length) {
        return;
      }
      parts.push(`<div class="section-label">${label}</div>`);
      items.forEach((c) => {
        parts.push(
          `<div class="chat-item ${c.id === activeId ? "active" : ""}" data-id="${c.id}">` +
            `<div class="meta"><strong>${MarkdownRenderer.escapeHtml(c.title)}</strong>` +
            `<small>${new Date(c.updatedAt).toLocaleString()}</small></div>` +
            `<button class="delete-btn" data-delete="${c.id}" title="删除" aria-label="删除">×</button>` +
            `</div>`,
        );
      });
    });

    $("#chatList").innerHTML =
      parts.join("") || `<div class="section-label">暂无对话</div>`;
  }

  function welcomeHtml() {
    return (
      `<div class="empty"><div class="empty-mark">${icon("i-chat")}</div>` +
      `<h1>有什么可以帮忙的？</h1>` +
      `<p>支持多轮对话、流式输出、图片/PDF/文本附件、Markdown 与代码高亮。记录保存在本机。</p>` +
      `</div>`
    );
  }

  function statusText(msg) {
    if (msg.status === "generating") {
      return "";
    }
    if (msg.status === "stopped") {
      return `<div class="status-tag stopped">已停止生成</div>`;
    }
    if (msg.status === "error") {
      return `<div class="status-tag error">生成出错</div>`;
    }
    return "";
  }

  function renderAttachmentPreview(list) {
    if (!list || !list.length) {
      return "";
    }
    const items = list
      .map((f) => {
        if (f.kind === "image" && f.previewUrl) {
          return `<img src="${f.previewUrl}" alt="${MarkdownRenderer.escapeHtml(f.name)}">`;
        }
        const label = f.kind === "document" ? "PDF" : "文件";
        return `<span class="msg-file-tag">${label} · ${MarkdownRenderer.escapeHtml(f.name)}</span>`;
      })
      .join("");
    return `<div class="msg-files">${items}</div>`;
  }

  function renderPendingAttachments() {
    const box = $("#attachments");
    if (!box) {
      return;
    }
    if (!pendingFiles.length) {
      box.innerHTML = "";
      return;
    }
    box.innerHTML = pendingFiles
      .map((f, i) => {
        const thumb =
          f.kind === "image" && f.previewUrl
            ? `<img src="${f.previewUrl}" alt="">`
            : "";
        return (
          `<span class="file-chip">${thumb}` +
          `<span class="meta">${MarkdownRenderer.escapeHtml(f.name)}</span>` +
          `<button type="button" data-remove-file="${i}" aria-label="移除">×</button></span>`
        );
      })
      .join("");
  }

  function renderMessages() {
    const c = current();
    const box = $("#messages");
    if (!c || !c.messages.length) {
      box.innerHTML = welcomeHtml();
      return;
    }

    box.innerHTML = c.messages
      .map((m, i) => {
        const isUser = m.role === "user";
        const streaming = m.status === "generating";
        const filesHtml = isUser ? renderAttachmentPreview(m.attachments) : "";
        const bodyText = m.content || "";
        const body = isUser
          ? bodyText
            ? MarkdownRenderer.escapeHtml(bodyText)
            : filesHtml
              ? `<span style="color:var(--muted);font-size:12px">已发送附件</span>`
              : ""
          : MarkdownRenderer.render(m.content, streaming);
        return (
          `<article class="message ${isUser ? "user" : ""}" data-index="${i}">` +
          `<div class="avatar">${isUser ? "我" : "AI"}</div>` +
          `<div class="bubble">` +
          filesHtml +
          `<div class="bubble-body ${isUser ? "" : "markdown "} ${streaming ? "typing" : ""}">${body}</div>` +
          statusText(m) +
          `<div class="message-actions">` +
          `<button type="button" data-copy="${i}" title="复制">复制</button>` +
          `</div></div></article>`
        );
      })
      .join("");

    box.scrollTop = box.scrollHeight;
  }

  function readFileAsDataUrl(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ""));
      reader.onerror = () => reject(new Error("读取文件失败"));
      reader.readAsDataURL(file);
    });
  }

  function readFileAsText(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ""));
      reader.onerror = () => reject(new Error("读取文件失败"));
      reader.readAsText(file, "utf-8");
    });
  }

  function extName(name) {
    const idx = name.lastIndexOf(".");
    return idx >= 0 ? name.slice(idx + 1).toLowerCase() : "";
  }

  function parseDataUrl(dataUrl) {
    const match = /^data:([^;]+);base64,(.+)$/s.exec(dataUrl || "");
    if (!match) {
      return null;
    }
    return { mediaType: match[1], data: match[2] };
  }

  async function addFiles(fileList) {
    const files = [...fileList];
    for (const file of files) {
      if (pendingFiles.length >= MAX_FILES) {
        toast(`最多上传 ${MAX_FILES} 个文件`);
        break;
      }
      const type = (file.type || "").toLowerCase();
      const ext = extName(file.name);

      if (IMAGE_TYPES.has(type) || ["jpg", "jpeg", "png", "gif", "webp"].includes(ext)) {
        if (file.size > MAX_IMAGE_BYTES) {
          toast(`${file.name} 超过 4MB，已跳过`);
          continue;
        }
        const dataUrl = await readFileAsDataUrl(file);
        const parsed = parseDataUrl(dataUrl);
        if (!parsed) {
          toast(`${file.name} 读取失败`);
          continue;
        }
        pendingFiles.push({
          kind: "image",
          name: file.name,
          mediaType: parsed.mediaType,
          data: parsed.data,
          previewUrl: dataUrl,
        });
        continue;
      }

      if (type === "application/pdf" || ext === "pdf") {
        if (file.size > MAX_DOC_BYTES) {
          toast(`${file.name} 超过 8MB，已跳过`);
          continue;
        }
        const dataUrl = await readFileAsDataUrl(file);
        const parsed = parseDataUrl(dataUrl);
        if (!parsed) {
          toast(`${file.name} 读取失败`);
          continue;
        }
        pendingFiles.push({
          kind: "document",
          name: file.name,
          mediaType: "application/pdf",
          data: parsed.data,
        });
        continue;
      }

      if (TEXT_EXT.has(ext) || type.startsWith("text/")) {
        if (file.size > MAX_TEXT_BYTES) {
          toast(`${file.name} 超过 1MB，已跳过`);
          continue;
        }
        const text = await readFileAsText(file);
        pendingFiles.push({
          kind: "text",
          name: file.name,
          text,
        });
        continue;
      }

      toast(`暂不支持：${file.name}`);
    }
    renderPendingAttachments();
  }

  function buildApiContent(text, attachments) {
    const parts = [];
    const files = attachments || [];
    files.forEach((f) => {
      if (f.kind === "image") {
        parts.push({
          type: "image",
          media_type: f.mediaType,
          data: f.data,
          name: f.name,
        });
      } else if (f.kind === "document") {
        parts.push({
          type: "document",
          media_type: f.mediaType || "application/pdf",
          data: f.data,
          name: f.name,
        });
      }
    });

    const textChunks = [];
    if (text) {
      textChunks.push(text);
    }
    files
      .filter((f) => f.kind === "text")
      .forEach((f) => {
        textChunks.push(`【附件：${f.name}】\n${f.text}`);
      });
    const mergedText = textChunks.join("\n\n").trim();
    if (mergedText) {
      parts.push({ type: "text", text: mergedText });
    }

    if (!parts.length) {
      return null;
    }
    if (parts.length === 1 && parts[0].type === "text") {
      return parts[0].text;
    }
    return parts;
  }

  function setGeneratingUi(generating) {
    const btn = $("#sendBtn");
    if (generating) {
      btn.classList.add("stop");
      btn.innerHTML = "■";
      btn.setAttribute("aria-label", "停止生成");
      btn.title = "停止生成";
      $("#prompt").disabled = true;
      $("#attachBtn").disabled = true;
    } else {
      btn.classList.remove("stop");
      btn.innerHTML = icon("i-send");
      btn.setAttribute("aria-label", "发送");
      btn.title = "发送";
      $("#prompt").disabled = false;
      $("#attachBtn").disabled = false;
    }
  }

  function newChat() {
    if (abortController) {
      abortController.abort();
      abortController = null;
    }
    const c = ChatStorage.createConversation("新对话");
    conversations.unshift(c);
    activeId = c.id;
    persist();
    renderChats();
    renderMessages();
    closeMobileSidebar();
    $("#prompt").focus();
  }

  function deleteChat(id) {
    conversations = conversations.filter((c) => c.id !== id);
    if (activeId === id) {
      activeId = conversations[0] ? conversations[0].id : null;
    }
    ensureActive();
    persist();
    renderChats();
    renderMessages();
  }

  function closeMobileSidebar() {
    $("#sidebar").classList.remove("open");
    $("#backdrop").classList.remove("show");
  }

  function buildApiMessages(conv) {
    // 不包含最后一条 generating 的 assistant
    return conv.messages
      .slice(0, -1)
      .filter((m) => m.role === "user" || m.role === "assistant")
      .filter((m) => {
        if (m.status === "error" && !m.content) {
          return false;
        }
        if (m.role === "user") {
          return Boolean(m.content) || (m.attachments && m.attachments.length);
        }
        return Boolean(m.content);
      })
      .map((m) => {
        if (m.role === "assistant") {
          return { role: "assistant", content: m.content || "" };
        }
        const apiContent = buildApiContent(m.content || "", m.attachments || []);
        return { role: "user", content: apiContent };
      })
      .filter((m) => m.content);
  }

  async function send() {
    const text = $("#prompt").value.trim();
    if ((!text && !pendingFiles.length) || abortController) {
      return;
    }

    ensureActive();
    const conv = current();
    if (!conv) {
      return;
    }

    const attachments = pendingFiles.map((f) => ({ ...f }));
    const displayText = text;

    if (!displayText && !attachments.length) {
      return;
    }

    const userMsg = ChatStorage.createMessage(
      "user",
      displayText,
      "completed",
      attachments,
    );
    conv.messages.push(userMsg);
    if (conv.messages.filter((m) => m.role === "user").length === 1) {
      conv.title = (text || attachments[0]?.name || "新对话").slice(0, 30);
    }
    $("#prompt").value = "";
    $("#prompt").style.height = "auto";
    pendingFiles = [];
    renderPendingAttachments();

    const assistantMsg = ChatStorage.createMessage("assistant", "", "generating");
    conv.messages.push(assistantMsg);
    conv.updatedAt = Date.now();
    persist();
    renderChats();
    renderMessages();
    setGeneratingUi(true);

    abortController = new AbortController();
    const history = buildApiMessages(conv);

    const result = await SseClient.streamChat({
      url: CHAT_URL,
      body: { messages: history, model: selectedModel || undefined },
      signal: abortController.signal,
      onDelta: (delta) => {
        assistantMsg.content += delta;
        renderMessages();
      },
      onError: (message) => {
        if (!assistantMsg.content) {
          assistantMsg.content = message;
        } else {
          assistantMsg.content += `\n\n[${message}]`;
        }
        assistantMsg.status = "error";
        toast(message);
      },
    });

    if (result.aborted) {
      assistantMsg.status = "stopped";
      if (!assistantMsg.content) {
        assistantMsg.content = "（已停止生成）";
      }
    } else if (assistantMsg.status === "generating") {
      assistantMsg.status = result.error ? "error" : "completed";
    }

    abortController = null;
    conv.updatedAt = Date.now();
    persist();
    setGeneratingUi(false);
    renderChats();
    renderMessages();
  }

  function stopGeneration() {
    if (abortController) {
      abortController.abort();
    }
  }

  function bind() {
    $("#newChat").onclick = () => newChat();
    $("#themeBtn").onclick = () => cycleTheme();
    $("#modelSelect").onchange = (e) => {
      selectedModel = e.target.value;
      ChatStorage.setSelectedModel(selectedModel);
      toast(`已切换模型：${selectedModel}`);
    };
    $("#attachBtn").onclick = () => $("#fileInput").click();
    $("#fileInput").onchange = async (e) => {
      const files = e.target.files;
      if (files && files.length) {
        try {
          await addFiles(files);
        } catch (err) {
          console.error(err);
          toast("添加附件失败");
        }
      }
      e.target.value = "";
    };
    $("#attachments").onclick = (e) => {
      const btn = e.target.closest("[data-remove-file]");
      if (!btn) {
        return;
      }
      pendingFiles.splice(+btn.dataset.removeFile, 1);
      renderPendingAttachments();
    };
    $("#sendBtn").onclick = () => {
      if (abortController) {
        stopGeneration();
      } else {
        send();
      }
    };

    $("#prompt").onkeydown = (e) => {
      if (e.key === "Enter" && !e.shiftKey && !e.isComposing && e.keyCode !== 229) {
        e.preventDefault();
        send();
      }
    };

    $("#prompt").oninput = (e) => {
      e.target.style.height = "auto";
      e.target.style.height = `${Math.min(e.target.scrollHeight, 180)}px`;
    };

    $("#openSidebar").onclick = () => {
      if (window.innerWidth <= 700) {
        const open = $("#sidebar").classList.toggle("open");
        $("#backdrop").classList.toggle("show", open);
      } else {
        $(".app").classList.toggle("sidebar-collapsed");
      }
    };

    $("#backdrop").onclick = () => closeMobileSidebar();
    $("[data-close='sidebar']").onclick = () => closeMobileSidebar();

    $("#chatList").onclick = (e) => {
      const del = e.target.closest("[data-delete]");
      if (del) {
        e.stopPropagation();
        if (confirm("确定删除该对话？")) {
          deleteChat(del.dataset.delete);
        }
        return;
      }
      const item = e.target.closest("[data-id]");
      if (item) {
        activeId = item.dataset.id;
        persist();
        renderChats();
        renderMessages();
        closeMobileSidebar();
      }
    };

    $("#messages").onclick = (e) => {
      const codeCopy = e.target.closest("[data-copy-code]");
      if (codeCopy) {
        const code =
          codeCopy.closest(".code-block")?.querySelector("code")?.textContent || "";
        navigator.clipboard?.writeText(code).then(() => {
          codeCopy.textContent = "已复制";
          setTimeout(() => {
            codeCopy.textContent = "复制代码";
          }, 1400);
          toast("已复制代码");
        });
        return;
      }
      const cp = e.target.closest("[data-copy]");
      if (cp) {
        const msg = current()?.messages[+cp.dataset.copy];
        if (msg) {
          navigator.clipboard?.writeText(msg.content);
          toast("已复制");
        }
      }
    };

    window
      .matchMedia("(prefers-color-scheme: dark)")
      .addEventListener("change", () => {
        if (themeMode === "system") {
          applyTheme();
        }
      });
  }

  async function init() {
    const data = ChatStorage.loadAll();
    conversations = data.conversations || [];
    activeId = data.activeId;
    themeMode = ChatStorage.getTheme();
    ensureActive();
    applyTheme();
    MarkdownRenderer.setupMarked();
    bind();
    await loadModels();
    renderChats();
    renderMessages();
    $("#prompt").focus();
  }

  init();
})();
