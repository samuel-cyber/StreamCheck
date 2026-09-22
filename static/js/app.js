/* Shared app JS: theme, API helper, utilities. */
(() => {
  // --- Theme: dark-first with manual override -------------------------------
  const KEY = "riparia-theme";
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  const stored = localStorage.getItem(KEY);
  const theme = stored || (prefersDark ? "dark" : "light");
  document.documentElement.setAttribute("data-theme", theme);

  window.RipariaTheme = {
    get: () => document.documentElement.getAttribute("data-theme"),
    toggle() {
      const next = this.get() === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      localStorage.setItem(KEY, next);
      document.dispatchEvent(new CustomEvent("riparia:theme", { detail: next }));
    },
  };

  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-theme-toggle]").forEach((btn) => {
      const sync = () => btn.setAttribute("aria-pressed", RipariaTheme.get() === "dark");
      btn.addEventListener("click", () => { RipariaTheme.toggle(); sync(); });
      sync();
    });
  });

  // --- API helper: consistent error envelope --------------------------------
  window.api = async function api(path, opts = {}) {
    const res = await fetch(path, { credentials: "same-origin", ...opts });
    let body = null;
    try { body = await res.json(); } catch { /* non-JSON */ }
    if (!res.ok) {
      const detail = body && body.detail;
      const message =
        (detail && typeof detail === "object" && detail.message) ||
        (typeof detail === "string" ? detail : null) ||
        (body && body.error && body.error.message) ||
        `Request failed (${res.status})`;
      const err = new Error(message);
      err.status = res.status;
      throw err;
    }
    return body;
  };

  window.escapeHtml = (s) => {
    const d = document.createElement("div");
    d.textContent = String(s ?? "");
    return d.innerHTML;
  };
})();
