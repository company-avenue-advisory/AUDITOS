/**
 * API Fetch utilities with JWT authentication headers.
 * 
 * NOTE: The global fetch interceptor defined in `AuthGuard.tsx` automatically
 * injects the `Authorization: Bearer <token>` header into all API requests
 * targeting the backend, so standard `fetch` calls will work out-of-the-box.
 * 
 * Use the helpers below if you need manual header builders or explicit client wrappers.
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * Returns authorization headers if token exists in localStorage.
 */
export function getAuthHeaders(headers: HeadersInit = {}): Headers {
  const reqHeaders = new Headers(headers);
  if (!reqHeaders.has("Content-Type")) {
    reqHeaders.set("Content-Type", "application/json");
  }

  if (typeof window !== "undefined") {
    const token = localStorage.getItem("token");
    if (token) {
      reqHeaders.set("Authorization", `Bearer ${token}`);
    }
  }
  return reqHeaders;
}

/**
 * Explicit fetch wrapper with token injection and 401 handling.
 */
export async function apiRequest(endpoint: string, options: RequestInit = {}): Promise<Response> {
  const url = endpoint.startsWith("http") ? endpoint : `${API_BASE_URL}${endpoint}`;
  
  const headers = getAuthHeaders(options.headers);
  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (response.status === 401 && typeof window !== "undefined") {
    localStorage.removeItem("token");
    localStorage.removeItem("user_email");
    localStorage.removeItem("user_role");
    window.location.href = "/login";
  }

  return response;
}
