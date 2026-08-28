import { MessageCircle, Palette, Globe, CalendarCheck, Sliders, type LucideIcon } from 'lucide-react'
import { clsx } from 'clsx'

export type SettingsTab = 'personality' | 'appearance' | 'languages' | 'booking' | 'advanced'

// Frequency order: roughly most-frequently-tuned to least. Icon/label
// styling deliberately mirrors Sidebar.tsx's own NavLink (rounded-xl px-3
// py-2, active = brand-gradient text-white shadow-sm, inactive =
// text-slate-600 hover:bg-slate-50) -- this is local, in-page navigation
// rather than routing, so plain buttons instead of router NavLink, but the
// same visual language as the app's one existing nav pattern.
const SECTIONS: { key: SettingsTab; label: string; icon: LucideIcon }[] = [
  { key: 'personality', label: 'Personality', icon: MessageCircle },
  { key: 'appearance', label: 'Appearance', icon: Palette },
  { key: 'languages', label: 'Languages', icon: Globe },
  { key: 'booking', label: 'Booking', icon: CalendarCheck },
  { key: 'advanced', label: 'Advanced', icon: Sliders },
]

export function isSettingsTab(value: string | null): value is SettingsTab {
  return !!value && SECTIONS.some((s) => s.key === value)
}

interface Props {
  active: SettingsTab
  onChange: (tab: SettingsTab) => void
}

export function SettingsNav({ active, onChange }: Props) {
  return (
    <nav
      className="flex gap-2 overflow-x-auto pb-1 md:w-56 md:flex-shrink-0 md:flex-col md:gap-1 md:overflow-visible md:pb-0"
      aria-label="Settings sections"
    >
      {SECTIONS.map(({ key, label, icon: Icon }) => {
        const isActive = key === active
        return (
          <button
            key={key}
            type="button"
            onClick={() => onChange(key)}
            aria-current={isActive ? 'page' : undefined}
            className={clsx(
              'flex flex-shrink-0 items-center gap-3 whitespace-nowrap rounded-xl px-3 py-2 text-base font-medium transition-colors',
              isActive
                ? 'brand-gradient text-white shadow-sm shadow-brand-200'
                : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
            )}
          >
            <Icon size={18} className={isActive ? 'text-white' : 'text-slate-400'} />
            {label}
          </button>
        )
      })}
    </nav>
  )
}
