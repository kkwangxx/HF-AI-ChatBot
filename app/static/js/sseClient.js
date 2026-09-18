/**
 * SSE 流式客户端。
 * UI 层只关心 onDelta / onError / onDone，不直接解析 SSE 协议细节。
 */
(function (global) {
  "use strict";

  /**
   * @param {object} options
   * @param {string} options.url
   * @param {object} options.body
   * @param {AbortSignal} [options.signal]
   * @param {(text: string) => void} options.onDelta
   * @param {(message: string) => void} options.onError
   * @param {() => void} [options.onDone]
   */
  async function streamChat(options) {
    const { url, body, signal, onDelta, onError, onDone } = options;

    let response;
    try {
      response = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "text/event-stream",
        },
        body: JSON.stringify(body),
        signal,
      });
    } catch (err) {
      if (err && err.name === "AbortError") {
        return { aborted: true };
      }
      onError("网络异常，无法连接服务器。");
      return { aborted: false, error: true };
    }

    if (!response.ok) {
      let detail = "";
      try {
        detail = await response.text();
      } catch (_) {
        /* ignore */
      }
      onError(mapHttpError(response.status, detail));
      return { aborted: false, error: true, status: response.status };
    }

    if (!response.body) {
      onError("服务器未返回流式响应。");
      return { aborted: false, error: true };
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";
    let gotError = false;

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          break;
        }
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed || !trimmed.startsWith("data:")) {
            continue;
          }
          const data = trimmed.slice(5).trim();
          if (!data) {
            continue;
          }
          if (data === "[DONE]") {
            if (onDone) {
              onDone();
            }
            return { aborted: false, error: gotError };
          }

          try {
            const parsed = JSON.parse(data);
            if (parsed.error && parsed.error.message) {
              gotError = true;
              onError(parsed.error.message);
              continue;
            }
            const delta =
              parsed.choices &&
              parsed.choices[0] &&
              parsed.choices[0].delta &&
              parsed.choices[0].delta.content;
            if (typeof delta === "string" && delta.length > 0) {
              onDelta(delta);
            }
          } catch (_) {
            /* 忽略非 JSON 片段 */
          }
        }
      }
    } catch (err) {
      if (err && err.name === "AbortError") {
        return { aborted: true };
      }
      gotError = true;
      onError("流式输出中断，已保留已生成内容。");
      return { aborted: false, error: true };
    }

    if (onDone) {
      onDone();
    }
    return { aborted: false, error: gotError };
  }

  function mapHttpError(status, detail) {
    const hints = {
      400: "请求参数有误。",
      401: "未授权，请检查服务端 API Key。",
      403: "没有权限访问。",
      404: "接口不存在。",
      429: "请求过于频繁，请稍后再试。",
      500: "服务器内部错误。",
      502: "网关错误。",
      503: "服务暂时不可用。",
    };
    const hint = hints[status] || `请求失败（HTTP ${status}）`;
    const short = (detail || "").replace(/\s+/g, " ").slice(0, 120);
    return short ? `${hint} ${short}` : hint;
  }

  global.SseClient = {
    streamChat,
  };
})(window);
