import { NavLink } from 'react-router-dom'
import { LayoutDashboard, MessageSquare, BookOpen, FileText, ShoppingBag, Users, Settings, CreditCard, LogOut, X, ShieldCheck, Sparkles, Star } from 'lucide-react'
import { useAuthStore } from '../../shared/store/authStore'
import { clsx } from 'clsx'

const nav = [
  { to: '/dashboard', icon: LayoutDashboard, label: 'Overview', color: 'text-violet-500' },
  { to: '/dashboard/conversations', icon: MessageSquare, label: 'Conversations', color: 'text-blue-500' },
  { to: '/dashboard/faqs', icon: BookOpen, label: 'FAQs', color: 'text-emerald-500' },
  { to: '/dashboard/documents', icon: FileText, label: 'Documents', color: 'text-amber-500' },
  { to: '/dashboard/products', icon: ShoppingBag, label: 'Products', color: 'text-indigo-500' },
  { to: '/dashboard/seo', icon: Sparkles, label: 'SEO Copywriter', color: 'text-fuchsia-500' },
  { to: '/dashboard/reviews', icon: Star, label: 'Review & Reputation', color: 'text-yellow-500' },
  { to: '/dashboard/leads', icon: Users, label: 'Leads', color: 'text-pink-500' },
  { to: '/dashboard/plan', icon: CreditCard, label: 'Plan & Billing', color: 'text-orange-500' },
  { to: '/dashboard/settings', icon: Settings, label: 'Settings', color: 'text-slate-500' },
]

interface Props {
  open: boolean
  onClose: () => void
}

export function Sidebar({ open, onClose }: Props) {
  const logout = useAuthStore((s) => s.logout)
  const isPlatformAdmin = useAuthStore((s) => s.user?.is_platform_admin)

  return (
    <>
      {/* Backdrop: mobile-only, shown while the drawer is open */}
      {open && (
        <div
          className="fixed inset-0 z-30 bg-slate-900/40 md:hidden"
          onClick={onClose}
          aria-hidden="true"
        />
      )}
      <aside
        className={clsx(
          'fixed inset-y-0 left-0 z-40 w-60 flex-shrink-0 bg-white border-r border-slate-200 flex flex-col transition-transform duration-200 ease-out',
          'md:static md:translate-x-0',
          open ? 'translate-x-0' : '-translate-x-full'
        )}
      >
        <div className="flex items-center justify-between px-6 py-5 border-b border-slate-100">
          <span className="text-2xl font-bold tracking-tight">
            Mielikki<span className="brand-gradient-text">X</span>
          </span>
          <button
            onClick={onClose}
            aria-label="Close menu"
            className="text-slate-400 hover:text-slate-600 md:hidden"
          >
            <X size={22} />
          </button>
        </div>
        <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
          {nav.map(({ to, icon: Icon, label, color }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/dashboard'}
              onClick={onClose}
              className={({ isActive }) =>
                clsx(
                  'flex items-center gap-3 px-3 py-2 rounded-xl text-base font-medium transition-colors',
                  isActive
                    ? 'brand-gradient text-white shadow-sm shadow-brand-200'
                    : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                )
              }
            >
              {({ isActive }) => (
                <>
                  <Icon size={18} className={isActive ? 'text-white' : color} />
                  {label}
                </>
              )}
            </NavLink>
          ))}
        </nav>
        <div className="p-3 border-t border-slate-100 space-y-1">
          {isPlatformAdmin && (
            <NavLink
              to="/admin"
              className="flex items-center gap-3 px-3 py-2 rounded-xl text-base font-medium text-slate-600 hover:bg-slate-50 hover:text-slate-900 transition-colors"
            >
              <ShieldCheck size={18} className="text-slate-500" />
              Platform Admin
            </NavLink>
          )}
          <button
            onClick={logout}
            className="flex w-full items-center gap-3 px-3 py-2 rounded-xl text-base font-medium text-slate-600 hover:bg-slate-50 hover:text-red-600 transition-colors"
          >
            <LogOut size={18} />
            Log out
          </button>
        </div>
      </aside>
    </>
  )
}
