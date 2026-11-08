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

function fileIconLabel(type) {
  if (!type) return "FILE";
  if (type.startsWith("image/")) return "IMG";
  if (type.startsWith("video/")) return "VID";
  if (type.startsWith("audio/")) return "AUD";
  if (type.includes("pdf")) return "PDF";
  if (type.includes("zip")||type.includes("tar")||type.includes("gz")) return "ZIP";
  if (type.includes("text")||type.includes("json")) return "TXT";
  return "FILE";
}

// Returns an <img> for the file type. If the matching icon file does not
// exist yet, the <img> fails and falls back to a text label (DIR/IMG/...).
// Icons live in frontend/icon/: directory.png, image.png, video.png, sound.png,
// pdf.png, zip.png, text.png, unknown.png
function fileIcon(type, isFolder, size) {
  const label = isFolder ? "DIR" : fileIconLabel(type);
  let src = "icon/unknown.png";
  if (isFolder) src = "icon/directory.png";
  else if (type && type.startsWith("image/")) src = "icon/image.png";
  else if (type && type.startsWith("video/")) src = "icon/video.png";
  else if (type && type.startsWith("audio/")) src = "icon/sound.png";
  else if (type && type.includes("pdf")) src = "icon/pdf.png";
  else if (type && (type.includes("zip") || type.includes("tar") || type.includes("gz"))) src = "icon/zip.png";
  else if (type && (type.includes("text") || type.includes("json"))) src = "icon/text.png";
  return `<img src="${src}" alt="${label}" onerror="this.outerHTML='${label}'" style="width:${size}px;height:${size}px;object-fit:contain;"/>`;
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

