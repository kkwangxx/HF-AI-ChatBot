/**
 * Markdown 渲染（marked + highlight.js）。
 */
(function (global) {
  "use strict";

  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function highlightCode(code, lang) {
    if (!global.hljs) {
      return escapeHtml(code);
    }
    try {
      if (lang && hljs.getLanguage(lang)) {
        return hljs.highlight(code, { language: lang }).value;
      }
      return hljs.highlightAuto(code).value;
    } catch (_) {
      return escapeHtml(code);
    }
  }

  function setupMarked() {
    if (!global.marked) {
      return;
    }

    marked.use({
      gfm: true,
      breaks: true,
      renderer: {
        code({ text, lang }) {
          const language = (lang || "text").trim().split(/\s+/)[0] || "text";
          const highlighted = highlightCode(text, language);
          return (
            `<div class="code-block">` +
            `<div class="code-head"><span>${escapeHtml(language)}</span>` +
            `<button class="code-copy" type="button" data-copy-code="1">复制代码</button></div>` +
            `<pre><code class="hljs language-${escapeHtml(language)}">${highlighted}</code></pre>` +
            `</div>`
          );
        },
      },
      hooks: {
        postprocess(html) {
          return html
            .replace(/<table>/g, '<div class="table-wrap"><table>')
            .replace(/<\/table>/g, "</table></div>");
        },
      },
    });
  }

  function render(content, streaming) {
    if (streaming) {
      return `<span class="stream-plain">${escapeHtml(content || "")}</span>`;
    }
    if (!global.marked) {
      return escapeHtml(content || "");
    }
    try {
      return marked.parse(content || "");
    } catch (err) {
      console.error("Markdown 渲染失败", err);
      return escapeHtml(content || "");
    }
  }

  setupMarked();

  global.MarkdownRenderer = {
    render,
    escapeHtml,
    setupMarked,
  };
})(window);
