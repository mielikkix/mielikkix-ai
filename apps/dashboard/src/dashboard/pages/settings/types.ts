import type { ChangeEvent } from 'react'

// Shared shapes for every Settings section -- kept here instead of inline
// in SettingsPage.tsx now that the page splits into multiple section
// components (see SettingsPage.tsx's own comment on why: all data
// ownership stays in the parent, sections are presentational only, so the
// shapes need a home neither one "owns" any more).

export interface DayHours {
  open: string
  close: string
}

export interface BusinessHours {
  monday?: DayHours | null
  tuesday?: DayHours | null
  wednesday?: DayHours | null
  thursday?: DayHours | null
  friday?: DayHours | null
  saturday?: DayHours | null
  sunday?: DayHours | null
}

export const DAYS: { key: keyof BusinessHours; label: string }[] = [
  { key: 'monday', label: 'Monday' },
  { key: 'tuesday', label: 'Tuesday' },
  { key: 'wednesday', label: 'Wednesday' },
  { key: 'thursday', label: 'Thursday' },
  { key: 'friday', label: 'Friday' },
  { key: 'saturday', label: 'Saturday' },
  { key: 'sunday', label: 'Sunday' },
]

export interface CalendarStatus {
  connected: boolean
  calendar_id?: string
  google_account_email?: string | null
  connected_at?: string
}

export interface Settings {
  tone: string
  welcome_message: string
  fallback_message: string
  fallback_messages: Record<string, string>
  business_hours: BusinessHours | null
  contact_email: string | null
  contact_phone: string | null
  languages: string[]
  llm_provider: string
  llm_model: string | null
}

// Small curated list rather than every ISO code -- keeps the picker usable;
// extend as real demand shows up.
export const AVAILABLE_LANGUAGES = [
  { code: 'en', label: 'English' },
  { code: 'no', label: 'Norwegian' },
  { code: 'de', label: 'German' },
  { code: 'fr', label: 'French' },
  { code: 'es', label: 'Spanish' },
  { code: 'it', label: 'Italian' },
  { code: 'nl', label: 'Dutch' },
  { code: 'pl', label: 'Polish' },
  { code: 'pt', label: 'Portuguese' },
  { code: 'sv', label: 'Swedish' },
]

export interface Business {
  primary_color: string
}

// Curated, brand-friendly palette — first entry matches the platform's own default.
export const PRESET_COLORS = [
  '#ff6b00', // Orange (default)
  '#7c3aed', // Violet
  '#4f46e5', // Indigo
  '#2563eb', // Blue
  '#0d9488', // Teal
  '#059669', // Emerald
  '#d97706', // Amber
  '#e11d48', // Rose
  '#1e293b', // Slate
]

export const HEX_COLOR_REGEX = /^#[0-9A-Fa-f]{6}$/

export type FieldChangeEvent = ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>
