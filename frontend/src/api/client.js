/** Thin wrapper around fetch for the backend API (Vite proxies /api).
 * Attaches the stored bearer token automatically. */

export function getToken() {
  return localStorage.getItem("lc_token") ?? "";
}

export function setSession(token, user) {
  localStorage.setItem("lc_token", token);
  localStorage.setItem("lc_user", JSON.stringify(user));
}

export function clearSession() {
  localStorage.removeItem("lc_token");
  localStorage.removeItem("lc_user");
}

export function getUser() {
  try {
    return JSON.parse(localStorage.getItem("lc_user") ?? "null");
  } catch {
    return null;
  }
}

// API base: empty = same origin (local dev proxy). In production the frontend
// and API run as separate Vercel projects, so VITE_API_BASE points at the API.
const API_BASE = import.meta.env.VITE_API_BASE ?? "";

export async function api(path, options = {}) {
  const token = getToken();
  const headers = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(API_BASE + path, { headers, ...options });
  if (!res.ok) {
    let detail = await res.text();
    try {
      const parsed = JSON.parse(detail);
      detail = typeof parsed.detail === "string" ? parsed.detail : JSON.stringify(parsed.detail);
    } catch {
      /* keep raw text */
    }
    const err = new Error(`API ${res.status}: ${detail.slice(0, 300)}`);
    err.status = res.status;
    throw err;
  }
  // 204 No Content (deletes, impression beacons): nothing to parse.
  if (res.status === 204) return null;
  return res.json();
}
