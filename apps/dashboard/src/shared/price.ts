// Plan and agent prices are fixed NOK amounts per month, excluding 25% MVA
// (apps/api/app/core/plans.py / agent_catalog.py, mirroring the website's
// src/data/pricing.ts). No currency conversion.
export function formatNok(amount: number): string {
  return `NOK ${amount.toLocaleString('en-US')}`
}
