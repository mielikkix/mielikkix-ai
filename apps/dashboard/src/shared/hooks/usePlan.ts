import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'

export interface PlanLimits {
  max_websites: number | null
  max_conversations_per_month: number | null
  max_document_uploads: number | null
  max_products: number | null
  max_languages: number | null
  conversation_history_days: number | null
}

export interface PlanUsage {
  websites: number
  conversations_this_month: number
  documents: number
  products: number
}

export interface PlanFeatures {
  knowledge_base: boolean
  lead_capture: boolean
  analytics_tier: 'basic' | 'standard' | 'advanced'
  email_notifications: boolean
  whatsapp_notifications: boolean
  instagram_integration: boolean
  multi_currency: boolean
  custom_branding: boolean
  api_access: boolean
  api_access_addon_available: boolean
  priority_support: boolean
}

export interface PlanStatus {
  plan: string
  plan_name: string
  price_usd: number
  limits: PlanLimits
  usage: PlanUsage
  features: PlanFeatures
  api_access_addon: boolean
  not_yet_implemented: string[]
}

// Feature keys that are plan-gated but have no real backend integration
// yet (see NOT_YET_IMPLEMENTED_FEATURES in the backend's app/core/plans.py).
// The API returns this list too (plan.not_yet_implemented); this mirrors
// it locally so components can synchronously decide "locked" vs "coming soon"
// vs "available" without waiting on a second lookup.
export const COMING_SOON_FEATURES = new Set(['whatsapp_notifications', 'instagram_integration'])

export function usePlan() {
  return useQuery<PlanStatus>({
    queryKey: ['plan'],
    queryFn: () => api.get('/businesses/me/plan').then((r) => r.data),
  })
}

export interface PlanCatalogEntry {
  key: string
  name: string
  price_usd: number
  tagline: string
  limits: PlanLimits
  features: PlanFeatures
}

export function usePlanCatalog() {
  return useQuery<PlanCatalogEntry[]>({
    queryKey: ['plan-catalog'],
    queryFn: () => api.get('/businesses/plans').then((r) => r.data),
  })
}
