import { MessageCircle, Palette, Globe, CalendarCheck, Sliders, ShieldCheck, type LucideIcon } from 'lucide-react'
import { clsx } from 'clsx'
import { useEffect, useRef } from 'react'

export type SettingsTab = 'personality' | 'appearance' | 'languages' | 'booking' | 'advanced' | 'privacy'

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
  { key: 'privacy', label: 'Privacy & data', icon: ShieldCheck },
]

export function isSettingsTab(value: string | null): value is SettingsTab {
  return !!value && SECTIONS.some((s) => s.key === value)
}

interface Props {
  active: SettingsTab
  onChange: (tab: SettingsTab) => void
}

export function SettingsNav({ active, onChange }: Props) {
  // On narrow screens the tabs scroll horizontally; keep the active one
  // visible (e.g. arriving at ?tab=privacy from the deletion banner).
  const navRef = useRef<HTMLElement>(null)
  useEffect(() => {
    const reveal = () => {
      const nav = navRef.current
      const tab = nav?.querySelector<HTMLElement>('[aria-current="page"]')
      if (!nav || !tab) return
      const navBox = nav.getBoundingClientRect()
      const tabBox = tab.getBoundingClientRect()
      if (tabBox.right > navBox.right) nav.scrollLeft += tabBox.right - navBox.right
      else if (tabBox.left < navBox.left) nav.scrollLeft -= navBox.left - tabBox.left
    }
    reveal()
    // Tab widths settle after first paint (web font, icons), so reveal again
    // whenever the nav or the active tab changes size.
    const nav = navRef.current
    const tab = nav?.querySelector('[aria-current="page"]')
    if (!nav || !tab || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(reveal)
    observer.observe(nav)
    observer.observe(tab)
    return () => observer.disconnect()
  }, [active])

  return (
    <nav
      ref={navRef}
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
