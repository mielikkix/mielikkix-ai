import axios from 'axios'

// Dev: Vite's dev server proxies /api to localhost:8000 (see vite.config.ts),
// so same-origin '/api' works without CORS. Prod: frontend (app.mielikkix.ai)
// and backend (api.mielikkix.ai) are separate hosts, so this must be an
// absolute URL; withCredentials still works cross-subdomain since the auth
// cookie's SameSite=Lax only cares about the registrable domain (mielikkix.ai),
// not the full origin.
const baseURL = import.meta.env.VITE_API_URL ?? (import.meta.env.PROD ? 'https://api.mielikkix.ai/api' : '/api')

export const api = axios.create({
  baseURL,
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
})

// Routes that are meant to be visited while logged out -- a 401 from the
// silent checkAuth() call on these pages is expected, not a session expiry,
// so it must not bounce the user away before they can use the page (this
// used to nuke direct links to /register and /reset-password?token=...).
const PUBLIC_ROUTES = ['/login', '/register', '/forgot-password', '/reset-password']

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401 && !PUBLIC_ROUTES.includes(window.location.pathname)) {
      window.location.href = '/login'
    }
    // FastAPI/Pydantic validation errors (422) return `detail` as an array of
    // {loc, msg, type} objects instead of a string. Every call site reads
    // `detail` expecting a string and hands it straight to setError/JSX, so an
    // unnormalized array crashes the page (React can't render raw objects as
    // children). Normalize once here instead of patching every call site.
    const detail = err.response?.data?.detail
    if (Array.isArray(detail)) {
      err.response.data.detail = detail
        .map((d: { msg?: string }) => d.msg)
        .filter(Boolean)
        .join(' ')
    }
    return Promise.reject(err)
  }
)
