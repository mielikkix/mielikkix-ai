import { create } from 'zustand'
import { api } from '../api/client'
import { queryClient } from '../queryClient'
import { isLocale, type Locale } from '../i18n/core'
import { useLocaleStore } from '../i18n'

interface User {
  id: string
  email: string
  full_name: string
  role: string
  business_id: string
  is_platform_admin: boolean
  // GDPR Phase 4 (see dashboard/components/AccountNotices.tsx)
  pending_acceptance: string[]
  deletion_scheduled_for: string | null
  // Dashboard language ("en"/"nb"); null until the user picks one.
  locale: Locale | null
}

interface AuthState {
  user: User | null
  initialized: boolean
  checkAuth: () => Promise<void>
  login: (email: string, password: string) => Promise<void>
  register: (data: RegisterData) => Promise<void>
  logout: () => Promise<void>
  /** Switches the UI language and, when signed in, saves it on the user. */
  changeLocale: (locale: Locale) => Promise<void>
}

interface RegisterData {
  business_name: string
  business_slug: string
  industry: string
  full_name: string
  email: string
  password: string
  country: string
  terms_accepted: boolean
  age_confirmed: boolean
  marketing_opt_in: boolean
}

/**
 * After sign-in: the user's saved language wins. A user who never picked one
 * gets this browser's explicit choice saved on their account (so a language
 * chosen on the sign-in page survives to other devices); a merely detected
 * language is not written to the server.
 */
async function syncLocale(user: User): Promise<User> {
  const { locale, chosen, setLocale } = useLocaleStore.getState()
  if (isLocale(user.locale)) {
    if (user.locale !== locale) setLocale(user.locale)
    return user
  }
  if (!chosen) return user
  try {
    const { data } = await api.patch('/auth/me/preferences', { locale })
    return data
  } catch {
    return user
  }
}

// The session lives in an httpOnly cookie set by the backend (not
// localStorage — a cookie that JS can't read can't be stolen by an XSS
// bug), so on load/refresh we don't know if we're logged in until we ask.
export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  initialized: false,

  checkAuth: async () => {
    try {
      const { data } = await api.get('/auth/me')
      set({ user: await syncLocale(data), initialized: true })
    } catch {
      set({ user: null, initialized: true })
    }
  },

  login: async (email, password) => {
    const { data } = await api.post('/auth/login', { email, password })
    queryClient.clear()
    set({ user: await syncLocale(data), initialized: true })
  },

  register: async (data) => {
    // The language the sign-up page was shown in becomes the account's language.
    const locale = useLocaleStore.getState().locale
    const { data: user } = await api.post('/auth/register', { ...data, locale })
    queryClient.clear()
    set({ user, initialized: true })
  },

  logout: async () => {
    try {
      await api.post('/auth/logout')
    } finally {
      queryClient.clear()
      set({ user: null, initialized: true })
    }
  },

  changeLocale: async (locale) => {
    useLocaleStore.getState().setLocale(locale, { chosen: true })
    if (!get().user) return
    try {
      const { data } = await api.patch('/auth/me/preferences', { locale })
      set({ user: data })
    } catch {
      // Still applied (and remembered in this browser); saved on the next sign-in.
    }
  },
}))
