import { useState } from 'react'
import { NavLink, Link } from 'react-router-dom'
import { LayoutDashboard, Building2, Gauge, CalendarCheck, LogOut, ArrowLeftCircle, Menu, X } from 'lucide-react'
import { clsx } from 'clsx'
import { useAuthStore } from '../../shared/store/authStore'

const nav = [
  { to: '/admin', icon: LayoutDashboard, label: 'Overview' },
  { to: '/admin/businesses', icon: Building2, label: 'Businesses' },
  { to: '/admin/usage', icon: Gauge, label: 'Groq Usage' },
  { to: '/admin/bookings', icon: CalendarCheck, label: 'Bookings' },
]

/** Visually distinct (dark) from the tenant Sidebar, so it's never
 * mistaken for the regular business dashboard while navigating. */
export function AdminLayout({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false)
  const logout = useAuthStore((s) => s.logout)

  return (
    <div className="flex h-screen bg-slate-50 overflow-hidden">
      {open && (
        <div className="fixed inset-0 z-30 bg-slate-900/40 md:hidden" onClick={() => setOpen(false)} aria-hidden="true" />
      )}
      <aside
        className={clsx(
          'fixed inset-y-0 left-0 z-40 w-60 flex-shrink-0 bg-slate-900 border-r border-slate-800 flex flex-col transition-transform duration-200 ease-out',
          'md:static md:translate-x-0',
          open ? 'translate-x-0' : '-translate-x-full'
        )}
      >
        <div className="flex items-center justify-between px-6 py-5 border-b border-slate-800">
          <span className="text-xl font-bold tracking-tight text-white">
            Mielikki<span className="brand-gradient-text">X</span> <span className="text-slate-400 font-medium">Admin</span>
          </span>
          <button onClick={() => setOpen(false)} aria-label="Close menu" className="text-slate-400 hover:text-white md:hidden">
            <X size={22} />
          </button>
        </div>
        <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
          {nav.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/admin'}
              onClick={() => setOpen(false)}
              className={({ isActive }) =>
                clsx(
                  'flex items-center gap-3 px-3 py-2 rounded-xl text-base font-medium transition-colors',
                  isActive ? 'brand-gradient text-white shadow-sm' : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                )
              }
            >
              <Icon size={18} />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="p-3 border-t border-slate-800 space-y-1">
          <Link
            to="/dashboard"
            className="flex items-center gap-3 px-3 py-2 rounded-xl text-base font-medium text-slate-300 hover:bg-slate-800 hover:text-white transition-colors"
          >
            <ArrowLeftCircle size={18} />
            Back to my dashboard
          </Link>
          <button
            onClick={logout}
            className="flex w-full items-center gap-3 px-3 py-2 rounded-xl text-base font-medium text-slate-300 hover:bg-slate-800 hover:text-red-400 transition-colors"
          >
            <LogOut size={18} />
            Log out
          </button>
        </div>
      </aside>
      <div className="flex-1 flex flex-col overflow-hidden">
        <div className="flex items-center gap-3 border-b border-slate-200 bg-white px-4 py-3 md:hidden">
          <button onClick={() => setOpen(true)} aria-label="Open menu" className="text-slate-500 hover:text-slate-700">
            <Menu size={22} />
          </button>
          <span className="text-lg font-bold tracking-tight">
            Mielikki<span className="brand-gradient-text">X</span> Admin
          </span>
        </div>
        <main className="flex-1 overflow-y-auto p-4 md:p-8">{children}</main>
      </div>
    </div>
  )
}
