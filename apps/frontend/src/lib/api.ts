/**
 * Typed fetch wrapper for the FastAPI backend. Base URL from
 * NEXT_PUBLIC_API_URL. Every error path — network failure, a non-2xx
 * response, an unparsable body — normalizes into the single ApiError shape
 * below, so callers never branch on error type.
 *
 * Token storage (Phase 9): the CloudCare access_token — however it was
 * obtained (password+OTP, or the SSO callback via src/auth.ts) — lives in
 * TWO places, kept in sync by setToken(): localStorage, which this file
 * reads to attach Authorization headers, and a plain (non-httpOnly) cookie
 * on THIS app's own origin, which middleware.ts reads to gate protected
 * routes server-side. Neither store is httpOnly — the backend's own
 * access_token cookie (apps/api/routers/auth.py's _set_access_token_cookie)
 * IS httpOnly, but it's set on the API's origin (localhost:8007) and so is
 * never visible to this Next.js app's own server or middleware, which run
 * on a different origin (localhost:3000/3002).
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8007";
const TOKEN_STORAGE_KEY = "cloudcare_access_token";
const REQUEST_TIMEOUT_MS = 8000;
export const SESSION_COOKIE_NAME = "cloudcare_session";

export interface ApiError {
  /** 0 means the request never reached the server (network/CORS failure). */
  status: number;
  message: string;
  detail?: unknown;
}

export function isApiError(err: unknown): err is ApiError {
  return typeof err === "object" && err !== null && "status" in err && "message" in err;
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(TOKEN_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  if (typeof window === "undefined") return;
  try {
    if (token) window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
    else window.localStorage.removeItem(TOKEN_STORAGE_KEY);
  } catch {
    /* storage unavailable — session-only */
  }

  // Middleware (server-side) can only ever see a cookie, never
  // localStorage — this is what makes /dashboard, /onboarding and
  // /approvals protectable without a round-trip to the API on every nav.
  if (token) {
    const maxAge = 60 * 60 * 8; // 8h — comfortably under the backend JWT's own expiry
    document.cookie = `${SESSION_COOKIE_NAME}=1; path=/; max-age=${maxAge}; samesite=lax`;
  } else {
    document.cookie = `${SESSION_COOKIE_NAME}=; path=/; max-age=0; samesite=lax`;
  }
}

function extractMessage(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail?: unknown }).detail;
    if (typeof detail === "string") return detail;
  }
  return fallback;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(init.headers);
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  if (!headers.has("Content-Type") && init.body !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers, credentials: "include", signal: controller.signal });
  } catch (err) {
    const apiError: ApiError = {
      status: 0,
      message: err instanceof Error ? err.message : "Network error — could not reach the CloudCare API.",
    };
    throw apiError;
  } finally {
    window.clearTimeout(timeout);
  }

  let body: unknown = undefined;
  const contentType = response.headers.get("content-type") ?? "";
  if (response.status !== 204 && contentType.includes("application/json")) {
    try {
      body = await response.json();
    } catch {
      body = undefined;
    }
  }

  if (!response.ok) {
    const apiError: ApiError = {
      status: response.status,
      message: extractMessage(body, response.statusText || `Request failed (${response.status})`),
      detail: body,
    };
    throw apiError;
  }

  return body as T;
}

export const api = {
  get: <T>(path: string, init?: RequestInit) => request<T>(path, { ...init, method: "GET" }),
  post: <T>(path: string, body?: unknown, init?: RequestInit) =>
    request<T>(path, { ...init, method: "POST", body: body !== undefined ? JSON.stringify(body) : undefined }),
  put: <T>(path: string, body?: unknown, init?: RequestInit) =>
    request<T>(path, { ...init, method: "PUT", body: body !== undefined ? JSON.stringify(body) : undefined }),
  patch: <T>(path: string, body?: unknown, init?: RequestInit) =>
    request<T>(path, { ...init, method: "PATCH", body: body !== undefined ? JSON.stringify(body) : undefined }),
  delete: <T>(path: string, init?: RequestInit) => request<T>(path, { ...init, method: "DELETE" }),
};
