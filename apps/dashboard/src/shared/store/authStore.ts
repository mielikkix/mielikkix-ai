import { create } from 'zustand'
import { api } from '../api/client'
import { queryClient } from '../queryClient'

interface User {
  id: string
  email: string
  full_name: string
  role: string
  business_id: string
  is_platform_admin: boolean
}

interface AuthState {
  user: User | null
  initialized: boolean
  checkAuth: () => Promise<void>
  login: (email: string, password: string) => Promise<void>
  register: (data: RegisterData) => Promise<void>
  logout: () => Promise<void>
}

interface RegisterData {
  business_name: string
  business_slug: string
  industry: string
  full_name: string
  email: string
  password: string
}

// The session lives in an httpOnly cookie set by the backend (not
// localStorage — a cookie that JS can't read can't be stolen by an XSS
// bug), so on load/refresh we don't know if we're logged in until we ask.
export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  initialized: false,

  checkAuth: async () => {
    try {
      const { data } = await api.get('/auth/me')
      set({ user: data, initialized: true })
    } catch {
      set({ user: null, initialized: true })
    }
  },

  login: async (email, password) => {
    const { data } = await api.post('/auth/login', { email, password })
    queryClient.clear()
    set({ user: data, initialized: true })
  },

  register: async (data) => {
    const { data: user } = await api.post('/auth/register', data)
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
}))
