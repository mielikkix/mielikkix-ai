import { createRoot } from 'react-dom/client'
import { Widget } from './Widget'
import tailwindStyles from './widget-tailwind.css?inline'
import resetStyles from './widget.css?inline'

// Fallback when a business's embed snippet doesn't set data-api-url. In
// production the widget bundle is served from app.mielikkix.ai (built
// alongside the dashboard) but the API lives on the separate
// api.mielikkix.ai host, so unlike the dashboard's own axios client, the
// widget can't just derive its API origin from where its own script tag
// was loaded from -- it has to point at api.mielikkix.ai explicitly.
const DEFAULT_API_BASE_URL = import.meta.env.PROD ? 'https://api.mielikkix.ai' : 'http://localhost:8000'

// Must capture this synchronously, right now, while the script tag is still
// actively executing — document.currentScript reverts to null by the time
// DOMContentLoaded fires below, so reading it inside mount() would be too late.
const currentScript = document.currentScript as HTMLScriptElement | null

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
