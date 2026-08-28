import { useEffect, useState } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { Menu } from 'lucide-react'
import { LoginPage } from './dashboard/pages/LoginPage'
import { RegisterPage } from './dashboard/pages/RegisterPage'
import { ForgotPasswordPage } from './dashboard/pages/ForgotPasswordPage'
import { ResetPasswordPage } from './dashboard/pages/ResetPasswordPage'
import { DashboardPage } from './dashboard/pages/DashboardPage'
import { FAQsPage } from './dashboard/pages/FAQsPage'
import { DocumentsPage } from './dashboard/pages/DocumentsPage'
import { ProductsPage } from './dashboard/pages/ProductsPage'
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
import { useAuthStore } from './shared/store/authStore'

function DashboardLayout({ children }: { children: React.ReactNode }) {
  const [sidebarOpen, setSidebarOpen] = useState(false)

  return (
    <div className="flex h-screen bg-gray-50 overflow-hidden">
      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      <div className="flex-1 flex flex-col overflow-hidden">
        <div className="flex items-center gap-3 border-b border-slate-200 bg-white px-4 py-3 md:hidden">
          <button
            onClick={() => setSidebarOpen(true)}
            aria-label="Open menu"
            className="text-slate-500 hover:text-slate-700"
          >
            <Menu size={22} />
          </button>
          <span className="text-lg font-bold tracking-tight">
            Mielikki<span className="brand-gradient-text">X</span>
          </span>
        </div>
        <main className="flex-1 overflow-y-auto p-4 md:p-8">{children}</main>
      </div>
    </div>
  )
}

function RequireAuth({ children }: { children: React.ReactNode }) {
  const user = useAuthStore((s) => s.user)
  const initialized = useAuthStore((s) => s.initialized)
  if (!initialized) return null
  return user ? <>{children}</> : <Navigate to="/login" replace />
}

// Platform-operator-only area (see files/ARCHITECTURE.md §2.7) -- gated by
// is_platform_admin on the logged-in user, resolved server-side from
// PLATFORM_ADMIN_EMAILS (app/core/dependencies.py:require_platform_admin).
// A non-admin business user who lands here is bounced to their own
// dashboard, not the login page, since they're still authenticated.
function RequireAdmin({ children }: { children: React.ReactNode }) {
  const user = useAuthStore((s) => s.user)
  const initialized = useAuthStore((s) => s.initialized)
  if (!initialized) return null
  if (!user) return <Navigate to="/login" replace />
  if (!user.is_platform_admin) return <Navigate to="/dashboard" replace />
  return <>{children}</>
}

export function App() {
  const checkAuth = useAuthStore((s) => s.checkAuth)

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
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  )
}
