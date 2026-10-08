// Language choice: detection, persistence, the signed-in user's saved
// preference, and what the screens actually render. Runs in Node without a
// DOM library: window/localStorage/document are small stubs, and pages are
// rendered with react-dom/server.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'

const store = new Map<string, string>()
const doc = { documentElement: { lang: 'en' } }

function stubBrowser(search = '', language = 'en-US') {
  store.clear()
  vi.stubGlobal('localStorage', {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, v),
    removeItem: (k: string) => void store.delete(k),
  })
  vi.stubGlobal('window', { location: { search, pathname: '/login', href: '' } })
  vi.stubGlobal('navigator', { language })
  vi.stubGlobal('document', doc)
}

const api = { get: vi.fn(), post: vi.fn(), patch: vi.fn() }
vi.mock('../api/client', () => ({ api }))

async function freshModules() {
  vi.resetModules()
  const i18n = await import('./index')
  const auth = await import('../store/authStore')
  return { ...i18n, useAuthStore: auth.useAuthStore }
}

beforeEach(() => {
  api.get.mockReset()
  api.post.mockReset()
  api.patch.mockReset()
})
afterEach(() => {
  vi.unstubAllGlobals()
})

describe('initial language', () => {
  it('defaults to English', async () => {
    stubBrowser()
    const { detectInitialLocale } = await freshModules()
    expect(detectInitialLocale()).toBe('en')
  })

  it('follows a Norwegian browser', async () => {
    stubBrowser('', 'nb-NO')
    const { detectInitialLocale } = await freshModules()
    expect(detectInitialLocale()).toBe('nb')
  })

  it('takes ?lang=no from the Norwegian marketing site and remembers it', async () => {
    stubBrowser('?lang=no')
    const { detectInitialLocale } = await freshModules()
    expect(detectInitialLocale()).toBe('nb')
    expect(store.get('mielikkix:locale')).toBe('nb')
  })

  it("prefers this browser's earlier choice over the browser language", async () => {
    stubBrowser('', 'nb-NO')
    store.set('mielikkix:locale', 'en')
    const { detectInitialLocale } = await freshModules()
    expect(detectInitialLocale()).toBe('en')
  })
})

describe('choosing a language', () => {
  it('persists the choice and sets <html lang> before sign-in', async () => {
    stubBrowser()
    const { useAuthStore, useLocaleStore } = await freshModules()
    await useAuthStore.getState().changeLocale('nb')
    expect(useLocaleStore.getState().locale).toBe('nb')
    expect(store.get('mielikkix:locale')).toBe('nb')
    expect(doc.documentElement.lang).toBe('nb')
    expect(api.patch).not.toHaveBeenCalled() // nobody to save it on yet
  })

  it('saves the choice on the signed-in user', async () => {
    stubBrowser()
    const { useAuthStore } = await freshModules()
    useAuthStore.setState({ user: { id: 'u1', locale: 'en' } as never, initialized: true })
    api.patch.mockResolvedValue({ data: { id: 'u1', locale: 'nb' } })
    await useAuthStore.getState().changeLocale('nb')
    expect(api.patch).toHaveBeenCalledWith('/auth/me/preferences', { locale: 'nb' })
    expect(useAuthStore.getState().user?.locale).toBe('nb')
  })

  it("restores the user's saved language after sign-in, whatever this browser had", async () => {
    stubBrowser()
    store.set('mielikkix:locale', 'en')
    const { useAuthStore, useLocaleStore } = await freshModules()
    api.post.mockResolvedValue({ data: { id: 'u1', locale: 'nb' } })
    await useAuthStore.getState().login('a@b.no', 'secret-password')
    expect(useLocaleStore.getState().locale).toBe('nb')
    expect(api.patch).not.toHaveBeenCalled()
  })

  it("saves a language picked before sign-in on a user who hasn't chosen one", async () => {
    stubBrowser()
    const { useAuthStore } = await freshModules()
    await useAuthStore.getState().changeLocale('nb') // on the login page
    api.post.mockResolvedValue({ data: { id: 'u1', locale: null } })
    api.patch.mockResolvedValue({ data: { id: 'u1', locale: 'nb' } })
    await useAuthStore.getState().login('a@b.no', 'secret-password')
    expect(api.patch).toHaveBeenCalledWith('/auth/me/preferences', { locale: 'nb' })
  })

  // QA 2026-10-08, A-01: a signed-in user clicked Norsk on /register while
  // /auth/me was still loading; the answer then put the account's saved
  // English back, so the click looked like it did nothing.
  it('keeps a language picked while the session check is still loading, and saves it', async () => {
    stubBrowser()
    const { useAuthStore, useLocaleStore } = await freshModules()
    let answerMe!: (v: unknown) => void
    api.get.mockReturnValue(new Promise((resolve) => (answerMe = resolve)))
    api.patch.mockResolvedValue({ data: { id: 'u1', locale: 'nb' } })
    const checking = useAuthStore.getState().checkAuth()
    await useAuthStore.getState().changeLocale('nb')
    answerMe({ data: { id: 'u1', locale: 'en' } })
    await checking
    expect(useLocaleStore.getState().locale).toBe('nb')
    expect(store.get('mielikkix:locale')).toBe('nb')
    expect(api.patch).toHaveBeenCalledWith('/auth/me/preferences', { locale: 'nb' })
    expect(useAuthStore.getState().user?.locale).toBe('nb')
  })

  it('sends the sign-up page language with the registration', async () => {
    stubBrowser('?lang=no')
    const { useAuthStore } = await freshModules()
    api.post.mockResolvedValue({ data: { id: 'u1', locale: 'nb' } })
    await useAuthStore.getState().register({ email: 'a@b.no' } as never)
    expect(api.post).toHaveBeenCalledWith('/auth/register', expect.objectContaining({ locale: 'nb' }))
  })
})

describe('rendered screens', () => {
  // react-router's links warn that useLayoutEffect is a no-op in a server render; irrelevant here.
  beforeEach(() => {
    const original = console.error
    vi.spyOn(console, 'error').mockImplementation((...args: unknown[]) => {
      if (String(args[0]).includes('useLayoutEffect does nothing on the server')) return
      original(...args)
    })
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  const rawKey = /\b(auth|navigation|common|language)\.[a-z]+\.?[a-zA-Z]*/

  it('renders the sign-in page in Norwegian with an accessible language switch', async () => {
    stubBrowser('?lang=nb')
    await freshModules()
    const { LoginPage } = await import('../../dashboard/pages/LoginPage')
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>,
    )
    expect(html).toContain('Velkommen tilbake')
    expect(html).toContain('Logg inn')
    expect(html).toContain('role="group" aria-label="Språk"')
    expect(html).toContain('aria-pressed="true" class') // the active language is marked, not only coloured
    expect(html).toContain('lang="nb"')
    expect(html).toContain('https://mielikkix.ai/no/privacy/')
    expect(html).not.toMatch(rawKey)
  })

  it('renders the sign-up page in English by default', async () => {
    stubBrowser()
    await freshModules()
    const { RegisterPage } = await import('../../dashboard/pages/RegisterPage')
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <RegisterPage />
      </MemoryRouter>,
    )
    expect(html).toContain('Create your account')
    expect(html).toContain('Select your industry')
    expect(html).toContain('https://mielikkix.ai/terms/')
    expect(html).not.toMatch(rawKey)
  })

  it('renders the dashboard navigation in Norwegian', async () => {
    stubBrowser('?lang=nb')
    await freshModules()
    const { Sidebar } = await import('../../dashboard/components/Sidebar')
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <Sidebar open={false} onClose={() => {}} />
      </MemoryRouter>,
    )
    for (const label of ['Oversikt', 'Samtaler', 'Vanlige spørsmål', 'Innstillinger', 'Logg ut']) {
      expect(html).toContain(label)
    }
    expect(html).not.toMatch(rawKey)
  })
})
