/**
 * Stores the backend's HTTP Basic Auth header (see backend/app/security.py)
 * for the current browser tab session. The backend is the real security
 * boundary -- this only lets the frontend attach the credentials once a
 * person has entered them, since a plain fetch() to a different origin
 * does not trigger the browser's native Basic Auth prompt the way a page
 * navigation would.
 */
const STORAGE_KEY = "backend-auth-header";

export function getStoredAuthHeader(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.sessionStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

export function storeAuthHeader(username: string, password: string): void {
  const header = `Basic ${btoa(`${username}:${password}`)}`;
  try {
    window.sessionStorage.setItem(STORAGE_KEY, header);
  } catch {
    // sessionStorage unavailable (private mode, etc.) -- the header still
    // gets used for the current page's requests via the caller, it just
    // won't survive a reload.
  }
}

export function clearStoredAuthHeader(): void {
  try {
    window.sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // no-op
  }
}
