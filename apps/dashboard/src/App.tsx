import { useEffect, useState } from 'react'
import { Routes, Route, Navigate, Link, useLocation } from 'react-router-dom'
import { Loader2, Menu } from 'lucide-react'
import { LoginPage } from './dashboard/pages/LoginPage'
import { RegisterPage } from './dashboard/pages/RegisterPage'
import { ForgotPasswordPage } from './dashboard/pages/ForgotPasswordPage'
import { ResetPasswordPage } from './dashboard/pages/ResetPasswordPage'
import { DashboardPage } from './dashboard/pages/DashboardPage'
import { FAQsPage } from './dashboard/pages/FAQsPage'
import { DocumentsPage } from './dashboard/pages/DocumentsPage'
import { ProductsPage } from './dashboard/pages/ProductsPage'
import { SeoPage } from './dashboard/pages/SeoPage'
import { ReviewsPage } from './dashboard/pages/ReviewsPage'
import { EmailMarketingPage } from './dashboard/pages/EmailMarketingPage'
import { LeadsPage } from './dashboard/pages/LeadsPage'
import { ConversationsPage } from './dashboard/pages/ConversationsPage'
import { SettingsPage } from './dashboard/pages/SettingsPage'
import { PlanPage } from './dashboard/pages/PlanPage'
import { Sidebar } from './dashboard/components/Sidebar'
import { AdminLayout } from './dashboard/components/AdminLayout'
import { AdminOverviewPage } from './dashboard/pages/admin/AdminOverviewPage'
import { AdminBusinessesPage } from './dashboard/pages/admin/AdminBusinessesPage'
import { AdminBusinessDetailPage } from './dashboard/pages/admin/AdminBusinessDetailPage'
import { AdminUsagePage } from './dashboard/pages/admin/AdminUsagePage'
import { AdminBookingsPage } from './dashboard/pages/admin/AdminBookingsPage'
import { AdminTicketsPage } from './dashboard/pages/admin/AdminTicketsPage'
import { AdminArticlesPage } from './dashboard/pages/admin/AdminArticlesPage'
import { AdminArticleFormPage } from './dashboard/pages/admin/AdminArticleFormPage'
import { useAuthStore } from './shared/store/authStore'
import { AccountNotices } from './dashboard/components/AccountNotices'
import { useLocaleStore, useT } from './shared/i18n'
import { LanguageSwitcher } from './shared/components/LanguageSwitcher'

function DashboardLayout({ children }: { children: React.ReactNode }) {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const { t } = useT()

  return (
    <div className="flex h-screen bg-gray-50 overflow-hidden print:block print:h-auto print:overflow-visible">
      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      <div className="flex-1 flex flex-col overflow-hidden print:block print:overflow-visible">
        {/* Top bar: menu button + logo on mobile only (the sidebar has its own
            logo on desktop); the language switch sits top right at every width. */}
        <header className="flex items-center gap-3 border-b border-slate-200 bg-white px-4 py-3 md:px-8 md:py-2.5 print:hidden">
          <button
            onClick={() => setSidebarOpen(true)}
            aria-label={t('navigation.openMenu')}
            className="text-slate-500 hover:text-slate-700 md:hidden"
          >
            <Menu size={22} />
          </button>
          <span className="text-lg font-bold tracking-tight md:hidden">
            Mielikki<span className="brand-gradient-text">x</span>
          </span>
          <LanguageSwitcher compact className="ml-auto" />
        </header>
        {/* Printing an SEO audit report (SeoPage's own "Print / Save as PDF" button)
            must flow the FULL report across as many pages as needed -- the normal
            dashboard layout is a fixed-height scrollable panel (h-screen +
            overflow-y-auto), which would otherwise clip a printed report to
            whatever was visible on screen at print time. print:overflow-visible
            here (and on the two wrapping divs above) removes that clipping only
            for print output; on-screen scrolling behavior is unchanged. */}
        <AccountNotices />
        <main className="flex-1 overflow-y-auto p-4 md:p-8 print:overflow-visible print:p-0">{children}</main>
      </div>
    </div>
  )
}

// Shown while /auth/me is answering, instead of an empty page -- on a slow
// connection that took long enough to look like a blank screen (QA 2026-10-08, A-02).
function SessionLoading() {
  const { t } = useT()
  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50" role="status">
      <Loader2 size={28} className="animate-spin text-brand-600" aria-hidden="true" />
      <span className="sr-only">{t('common.loading')}</span>
    </div>
  )
}

function RequireAuth({ children }: { children: React.ReactNode }) {
  const user = useAuthStore((s) => s.user)
  const initialized = useAuthStore((s) => s.initialized)
  if (!initialized) return <SessionLoading />
  return user ? <>{children}</> : <Navigate to="/login" replace />
}

// Catch-all for an unmatched URL (typo, a removed/renamed route, a stale
// bookmark). A signed-in user gets a "Page not found" screen inside the
// dashboard, with the menu and a way back (QA 2026-10-08, A-02) -- never a
// bounce to /login, which used to end their session for a mistyped URL.
function NotFound() {
  const user = useAuthStore((s) => s.user)
  const initialized = useAuthStore((s) => s.initialized)
  const { t } = useT()
  if (!initialized) return <SessionLoading />
  if (!user) return <Navigate to="/login" replace />
  return (
    <DashboardLayout>
      <div className="mx-auto max-w-md py-16 text-center">
        <p className="text-5xl font-bold text-slate-300">404</p>
        <h1 className="mt-4 text-2xl font-bold text-slate-900">{t('notFound.title')}</h1>
        <p className="mt-2 text-slate-500">{t('notFound.text')}</p>
        <Link
          to="/dashboard"
          className="brand-gradient mt-6 inline-flex rounded-xl px-4 py-2 font-semibold text-white shadow-sm shadow-brand-200 hover:scale-[1.02] focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2"
        >
          {t('notFound.backToOverview')}
        </Link>
      </div>
    </DashboardLayout>
  )
}

// The bare domain: Overview when signed in, else the sign-in page.
function HomeRedirect() {
  const user = useAuthStore((s) => s.user)
  const initialized = useAuthStore((s) => s.initialized)
  if (!initialized) return <SessionLoading />
  return <Navigate to={user ? '/dashboard' : '/login'} replace />
}

// /no/<path> is how mielikkix.ai spells Norwegian, so people try it here too
// (QA 2026-10-08, A-01: /no/register was a blank page). Switch to Norsk and
// open the same page without the prefix.
function NorwegianPrefix() {
  const { pathname, search, hash } = useLocation()
  const setLocale = useLocaleStore((s) => s.setLocale)
  useEffect(() => setLocale('nb', { chosen: true }), [setLocale])
  const rest = pathname.replace(/^\/no(?=\/|$)/, '') || '/login'
  return <Navigate to={rest + search + hash} replace />
}

// Platform-operator-only area (see files/ARCHITECTURE.md §2.7) -- gated by
// is_platform_admin on the logged-in user, resolved server-side from
// PLATFORM_ADMIN_EMAILS (app/core/dependencies.py:require_platform_admin).
// A non-admin business user who lands here is bounced to their own
// dashboard, not the login page, since they're still authenticated.
function RequireAdmin({ children }: { children: React.ReactNode }) {
  const user = useAuthStore((s) => s.user)
  const initialized = useAuthStore((s) => s.initialized)
  if (!initialized) return <SessionLoading />
  if (!user) return <Navigate to="/login" replace />
  if (!user.is_platform_admin) return <Navigate to="/dashboard" replace />
  return <>{children}</>
}

export function App() {
  const checkAuth = useAuthStore((s) => s.checkAuth)
  const { t } = useT()

  // The browser tab title follows the UI language too.
  useEffect(() => {
    document.title = t('common.appTitle')
  }, [t])

  useEffect(() => {
    checkAuth()
  }, [checkAuth])

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route
        path="/dashboard"
        element={
          <RequireAuth>
            <DashboardLayout><DashboardPage /></DashboardLayout>
          </RequireAuth>
        }
      />
      <Route
        path="/dashboard/faqs"
        element={
          <RequireAuth>
            <DashboardLayout><FAQsPage /></DashboardLayout>
          </RequireAuth>
        }
      />
      <Route
        path="/dashboard/documents"
        element={
          <RequireAuth>
            <DashboardLayout><DocumentsPage /></DashboardLayout>
          </RequireAuth>
        }
      />
      <Route
        path="/dashboard/products"
        element={
          <RequireAuth>
            <DashboardLayout><ProductsPage /></DashboardLayout>
          </RequireAuth>
        }
      />
      <Route
        path="/dashboard/seo"
        element={
          <RequireAuth>
            <DashboardLayout><SeoPage /></DashboardLayout>
          </RequireAuth>
        }
      />
      <Route
        path="/dashboard/reviews"
        element={
          <RequireAuth>
            <DashboardLayout><ReviewsPage /></DashboardLayout>
          </RequireAuth>
        }
      />
      <Route
        path="/dashboard/email-marketing"
        element={
          <RequireAuth>
            <DashboardLayout><EmailMarketingPage /></DashboardLayout>
          </RequireAuth>
        }
      />
      <Route
        path="/dashboard/leads"
        element={
          <RequireAuth>
            <DashboardLayout><LeadsPage /></DashboardLayout>
          </RequireAuth>
        }
      />
      <Route
        path="/dashboard/conversations"
        element={
          <RequireAuth>
            <DashboardLayout><ConversationsPage /></DashboardLayout>
          </RequireAuth>
        }
      />
      <Route
        path="/dashboard/settings"
        element={
          <RequireAuth>
            <DashboardLayout><SettingsPage /></DashboardLayout>
          </RequireAuth>
        }
      />
      <Route
        path="/dashboard/plan"
        element={
          <RequireAuth>
            <DashboardLayout><PlanPage /></DashboardLayout>
          </RequireAuth>
        }
      />
      <Route
        path="/admin"
        element={
          <RequireAdmin>
            <AdminLayout><AdminOverviewPage /></AdminLayout>
          </RequireAdmin>
        }
      />
      <Route
        path="/admin/businesses"
        element={
          <RequireAdmin>
            <AdminLayout><AdminBusinessesPage /></AdminLayout>
          </RequireAdmin>
        }
      />
      <Route
        path="/admin/businesses/:businessId"
        element={
          <RequireAdmin>
            <AdminLayout><AdminBusinessDetailPage /></AdminLayout>
          </RequireAdmin>
        }
      />
      <Route
        path="/admin/usage"
        element={
          <RequireAdmin>
            <AdminLayout><AdminUsagePage /></AdminLayout>
          </RequireAdmin>
        }
      />
      <Route
        path="/admin/bookings"
        element={
          <RequireAdmin>
            <AdminLayout><AdminBookingsPage /></AdminLayout>
          </RequireAdmin>
        }
      />
      <Route
        path="/admin/tickets"
        element={
          <RequireAdmin>
            <AdminLayout><AdminTicketsPage /></AdminLayout>
          </RequireAdmin>
        }
      />
      <Route
        path="/admin/articles"
        element={
          <RequireAdmin>
            <AdminLayout><AdminArticlesPage /></AdminLayout>
          </RequireAdmin>
        }
      />
      <Route
        path="/admin/articles/new"
        element={
          <RequireAdmin>
            <AdminLayout><AdminArticleFormPage /></AdminLayout>
          </RequireAdmin>
        }
      />
      <Route
        path="/admin/articles/:id/edit"
        element={
          <RequireAdmin>
            <AdminLayout><AdminArticleFormPage /></AdminLayout>
          </RequireAdmin>
        }
      />
      <Route path="/" element={<HomeRedirect />} />
      <Route path="/no/*" element={<NorwegianPrefix />} />
      <Route path="/no" element={<NorwegianPrefix />} />
      <Route path="*" element={<NotFound />} />
    </Routes>
  )
}
