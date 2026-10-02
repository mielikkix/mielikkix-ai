// Business.status values are internal: "trial" means "active on the Free plan" (the
// API's gating checks status in ("active", "trial")). Free is a permanent plan, not a
// trial -- QA 2026-10-02 (D11/M7) -- so admins see these labels, never the raw value.
export const BUSINESS_STATUS_LABELS: Record<string, string> = {
  active: 'Active (paid)',
  trial: 'Free plan',
  suspended: 'Suspended',
}

export const businessStatusLabel = (status: string) => BUSINESS_STATUS_LABELS[status] ?? status
