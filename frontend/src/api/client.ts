export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

export const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

const CSRF_HEADER = 'X-CSRF-Token';
const UNSAFE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

// The frontend and backend are on different origins, so the CSRF token cannot be
// read from a cookie. It is returned by /auth/login and /auth/me, kept in memory
// here, and echoed back on every mutation.
let csrfToken: string | null = null;

export function setCsrfToken(token: string | null): void {
  csrfToken = token;
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${BASE_URL}${path.startsWith('/') ? path : `/${path}`}`;

  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData) && typeof options.body === 'string') {
    if (!headers.has('Content-Type')) {
      headers.set('Content-Type', 'application/json');
    }
  }

  const method = (options.method || 'GET').toUpperCase();
  if (csrfToken && UNSAFE_METHODS.has(method) && !headers.has(CSRF_HEADER)) {
    headers.set(CSRF_HEADER, csrfToken);
  }

  const response = await fetch(url, {
    ...options,
    credentials: 'include',
    headers,
  });

  if (response.status === 204) {
    return {} as T;
  }

  let data: unknown;
  const contentType = response.headers.get('content-type');
  if (contentType && contentType.includes('application/json')) {
    data = await response.json();
  } else {
    data = await response.text();
  }

  if (!response.ok) {
    let detail = 'An unknown error occurred';
    if (data && typeof data === 'object' && 'detail' in data) {
      const rawDetail = (data as Record<string, unknown>).detail;
      if (Array.isArray(rawDetail)) {
        detail = rawDetail
          .map((err) => {
            if (err && typeof err === 'object' && 'msg' in err) {
              const locStr = Array.isArray(err.loc) ? err.loc.join('.') : '';
              return locStr ? `${locStr}: ${err.msg}` : String(err.msg);
            }
            return JSON.stringify(err);
          })
          .join('; ');
      } else {
        detail = String(rawDetail);
      }
    } else if (typeof data === 'string' && data) {
      detail = data;
    } else {
      detail = response.statusText || 'An unknown error occurred';
    }
    throw new ApiError(response.status, detail);
  }

  return data as T;
}
