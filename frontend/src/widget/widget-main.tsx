import { createRoot } from 'react-dom/client'
import { Widget } from './Widget'
import tailwindStyles from './widget-tailwind.css?inline'
import resetStyles from './widget.css?inline'

// Last-resort only -- real embeds derive the API base from the script's own
// src origin below. This only applies if that derivation fails outright
// (e.g. document.currentScript unavailable).
const DEFAULT_API_BASE_URL = 'http://localhost:8000'

// Must capture this synchronously, right now, while the script tag is still
// actively executing — document.currentScript reverts to null by the time
// DOMContentLoaded fires below, so reading it inside mount() would be too late.
const currentScript = document.currentScript as HTMLScriptElement | null

function mount() {
  const script = currentScript
  const businessId = script?.dataset.business || script?.getAttribute('data-business')
  const primaryColor = script?.dataset.color
  const botName = script?.dataset.botName
  // The widget script and the API are always served from the same origin
  // (nginx proxies /api/* alongside the static build in production; Vite's
  // dev server proxies /api the same way locally) -- deriving the API base
  // from the script's own src means every embed snippet just works,
  // without needing a manually-added data-api-url on every business's site.
  // data-api-url still works as an explicit override (e.g. pointing a local
  // widget build at a different backend).
  const scriptOrigin = (() => {
    try {
      return script?.src ? new URL(script.src).origin : null
    } catch {
      return null
    }
  })()
  const apiBaseUrl = script?.dataset.apiUrl || scriptOrigin || DEFAULT_API_BASE_URL

  if (!businessId) {
    console.warn('[AgentNexus] Missing data-business attribute on widget script tag.')
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
  mountPoint.id = 'agentnexus-root'
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
