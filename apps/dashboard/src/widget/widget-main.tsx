import { createRoot } from 'react-dom/client'
import { Widget } from './Widget'
import tailwindStyles from './widget-tailwind.css?inline'
import resetStyles from './widget.css?inline'

const PROD_API_BASE_URL = 'https://api.mielikkix.ai'
const LOCAL_API_BASE_URL = 'http://localhost:8000'

// Must capture this synchronously, right now, while the script tag is still
// actively executing — document.currentScript reverts to null by the time
// DOMContentLoaded fires below, so reading it inside mount() would be too late.
const currentScript = document.currentScript as HTMLScriptElement | null

// Fallback when a business's embed snippet doesn't set data-api-url -- which
// is the normal case, since the snippet the dashboard hands out (see
// DashboardPage.tsx) deliberately stays minimal.
//
// In production the bundle is served from app.mielikkix.ai while the API is on
// the separate api.mielikkix.ai host, so we can't simply reuse the script's
// origin. But we can't hardcode the production host either: this bundle is
// ALWAYS built by `vite build` (there is no dev build of the widget), so
// import.meta.env.PROD is true even when it's served from localhost during
// development -- which made the dashboard's own snippet call production from a
// local page.
//
// So key off where the BUNDLE was loaded from, not the page's own origin: a
// widget.js served from localhost is one of ours being developed against a
// local backend. A customer developing their own site locally still loads the
// bundle from app.mielikkix.ai, so they correctly keep the production API.
function defaultApiBaseUrl(script: HTMLScriptElement | null): string {
  try {
    const { hostname } = new URL(script?.src ?? '', window.location.href)
    if (hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '::1') {
      return LOCAL_API_BASE_URL
    }
  } catch {
    // Malformed/missing src -- fall through to the production default.
  }
  return PROD_API_BASE_URL
}

const DEFAULT_API_BASE_URL = defaultApiBaseUrl(currentScript)

function mount() {
  const script = currentScript
  const businessId = script?.dataset.business || script?.getAttribute('data-business')
  const primaryColor = script?.dataset.color
  const botName = script?.dataset.botName
  // data-api-url overrides the default for local/self-hosted setups; every
  // hosted embed snippet just works against api.mielikkix.ai without needing
  // a manually-added data-api-url on every business's site.
  const apiBaseUrl = script?.dataset.apiUrl || DEFAULT_API_BASE_URL

  if (!businessId) {
    console.warn('[MielikkiX] Missing data-business attribute on widget script tag.')
    return
  }

  // Mounted inside a Shadow DOM so the widget's Tailwind styles never leak onto
  // (or get overridden by) the host page's own CSS.
  const host = document.createElement('div')
  document.body.appendChild(host)
  const shadow = host.attachShadow({ mode: 'open' })

  const style = document.createElement('style')
  style.textContent = `${tailwindStyles}\n${resetStyles}`
  shadow.appendChild(style)

  const mountPoint = document.createElement('div')
  mountPoint.id = 'mielikkix-root'
  shadow.appendChild(mountPoint)

  createRoot(mountPoint).render(
    <Widget businessId={businessId} primaryColor={primaryColor} botName={botName} apiBaseUrl={apiBaseUrl} />
  )
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', mount)
} else {
  mount()
}
