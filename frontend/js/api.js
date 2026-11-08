const API = window.location.origin;

const auth = {
  getToken() { return sessionStorage.getItem("token"); },
  setToken(t) { sessionStorage.setItem("token", t); },
  getUser() {
    try { return JSON.parse(sessionStorage.getItem("user")); } catch { return null; }
  },
  setUser(u) { sessionStorage.setItem("user", JSON.stringify(u)); },
  logout() {
    sessionStorage.removeItem("token");
    sessionStorage.removeItem("user");
    window.location.href = "/login.html";
  },
  require() {
    if (!this.getToken()) { window.location.href = "/login.html"; return false; }
    return true;
  }
};

async function apiFetch(path, options = {}) {
  const token = auth.getToken();
  const headers = { ...options.headers };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (!(options.body instanceof FormData)) headers["Content-Type"] = "application/json";
  const res = await fetch(`${API}${path}`, { ...options, headers });
  if (res.status === 401) { auth.logout(); return null; }
  return res;
}

function formatSize(b) {
  if (b == null) return "0 B";
  if (b < 1024) return `${b} B`;
  if (b < 1048576) return `${(b/1024).toFixed(1)} KB`;
  if (b < 1073741824) return `${(b/1048576).toFixed(1)} MB`;
  return `${(b/1073741824).toFixed(1)} GB`;
}

function formatDate(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function formatDateTime(iso) {
  if (!iso) return "Never";
  return new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" });
}

function fileEmoji(type) {
  if (!type) return "📄";
  if (type.startsWith("image/")) return "🖼️";
  if (type.startsWith("video/")) return "🎬";
  if (type.startsWith("audio/")) return "🎵";
  if (type.includes("pdf")) return "📕";
  if (type.includes("zip")||type.includes("tar")||type.includes("gz")) return "📦";
  if (type.includes("text")||type.includes("json")) return "📝";
  return "📄";
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function qs(sel, root = document) { return root.querySelector(sel); }
function qsa(sel, root = document) { return Array.from(root.querySelectorAll(sel)); }

function mediaUrl(fileId) {
  return `${API}/api/file/preview/${fileId}?token=${encodeURIComponent(auth.getToken() || "")}`;
}

function downloadUrl(fileId) {
  return `${API}/api/file/download/${fileId}?token=${encodeURIComponent(auth.getToken() || "")}`;
}

function folderZipUrl(fileId) {
  return `${API}/api/file/download-folder/${fileId}?token=${encodeURIComponent(auth.getToken() || "")}`;
}

function showAlert(el, msg, type = "error") { el.textContent = msg; el.className = `alert alert-${type} show`; }
function hideAlert(el) { el.className = "alert"; }

function toast(msg, type = "info") {
  let wrap = qs("#toasts");
  if (!wrap) {
    wrap = document.createElement("div");
    wrap.id = "toasts";
    document.body.appendChild(wrap);
  }
  const t = document.createElement("div");
  t.className = `win-toast win-toast-${type}`;
  t.textContent = msg;
  wrap.appendChild(t);
  setTimeout(() => t.classList.add("show"), 10);
  setTimeout(() => {
    t.classList.remove("show");
    setTimeout(() => t.remove(), 250);
  }, 3200);
}

