/** Authentication API calls for local login and Google OAuth session state. */
import { API_BASE, fetchWithTimeout, getAuthHeaders, handleResponse } from "./core/http.js";

export async function loginUser(email, project) {
  const res = await fetchWithTimeout(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, project })
  });
  return handleResponse(res);
}

export async function getCurrentUser() {
  try {
    const res = await fetchWithTimeout(`${API_BASE}/auth/me`, {
      method: "GET",
      headers: getAuthHeaders(),
      cache: "no-store"
    });
    if (!res.ok) return null;
    return await res.json();
  } catch (error) {
    console.warn("Auth check failed (likely no backend):", error);
    return null;
  }
}

export async function getGoogleAuthStartUrl(tokenOverride = "") {
  const res = await fetchWithTimeout(`${API_BASE}/auth/google/start`, {
    method: "GET",
    headers: getAuthHeaders(tokenOverride),
    cache: "no-store"
  });
  const data = await handleResponse(res);
  return data?.auth_url || "";
}

export async function getGoogleAuthStatus() {
  const res = await fetchWithTimeout(`${API_BASE}/auth/google/me`, {
    method: "GET",
    headers: getAuthHeaders(),
    cache: "no-store"
  });
  return handleResponse(res);
}

export async function logoutGoogleAuth() {
  const res = await fetchWithTimeout(`${API_BASE}/auth/google/logout`, {
    method: "POST",
    headers: getAuthHeaders()
  });
  return handleResponse(res);
}
