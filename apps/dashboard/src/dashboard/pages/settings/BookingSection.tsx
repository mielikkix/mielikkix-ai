import { UseMutationResult } from '@tanstack/react-query'
import { Card } from '../../../shared/components/Card'
import { Button } from '../../../shared/components/Button'
import { PlanGate } from '../../../shared/components/PlanGate'
import { api } from '../../../shared/api/client'
import { BusinessHours, CalendarStatus, DayHours, DAYS } from './types'

interface Props {
  bookingEnabled: boolean
  calendarBanner: 'connected' | 'error' | null
  calendarStatus: CalendarStatus | undefined
  disconnectCalendarMut: UseMutationResult<unknown, unknown, void>
  businessHours: BusinessHours
  setDayHours: (day: keyof BusinessHours, hours: DayHours | null) => void
  businessHoursMut: UseMutationResult<unknown, unknown, BusinessHours>
}

export function BookingSection({
  bookingEnabled,
  calendarBanner,
  calendarStatus,
  disconnectCalendarMut,
  businessHours,
  setDayHours,
  businessHoursMut,
}: Props) {
  // Gated as one whole section, not per-card: Business Hours only ever
  // means anything once Booking Assistant itself is unlocked, so a Free/
  // Basic business must never be able to fill it in and see "saved!" for
  // a feature they can't actually use yet -- that's confusing, not just
  // cosmetically inconsistent with the Booking Calendar card's own lock.
  if (!bookingEnabled) {
    return (
      <Card title="Booking Assistant">
        <PlanGate feature="booking_enabled">
          <span />
        </PlanGate>
      </Card>
    )
  }

  return (
    <div className="space-y-6">
      <Card title="Booking Calendar">
        <div className="space-y-3">
          {calendarBanner === 'connected' && (
            <p className="text-base text-green-600">Calendar connected!</p>
          )}
          {calendarBanner === 'error' && (
            <p className="text-base text-red-600">Couldn't connect your calendar. Please try again.</p>
          )}
          {calendarStatus?.connected ? (
            <>
              <p className="text-base text-slate-700">
                Connected
                {calendarStatus.google_account_email ? ` as ${calendarStatus.google_account_email}` : ''}.
              </p>
              <Button
                variant="secondary"
                loading={disconnectCalendarMut.isPending}
                onClick={() => disconnectCalendarMut.mutate()}
              >
                Disconnect
              </Button>
            </>
          ) : (
            <>
              <p className="text-sm text-slate-500">
                Connect your business's Google Calendar so Booking Assistant can check real
                availability and create real appointments on it.
              </p>
              <Button
                onClick={() => {
                  window.location.href = `${api.defaults.baseURL}/businesses/me/calendar/authorize`
                }}
              >
                Connect Google Calendar
              </Button>
            </>
          )}
        </div>
      </Card>

      <Card title="Business Hours">
        <div className="space-y-3">
          <p className="text-sm text-slate-500">
            When Booking Assistant offers appointment times to visitors. A day left closed is never offered.
          </p>
          {DAYS.map(({ key, label }) => {
            const hours = businessHours[key]
            const isOpen = !!hours
            return (
              <div key={key} className="flex items-center gap-3">
                <label className="flex w-32 items-center gap-2 text-base text-slate-700">
                  <input
                    type="checkbox"
                    checked={isOpen}
                    onChange={(e) =>
                      setDayHours(key, e.target.checked ? { open: '09:00', close: '17:00' } : null)
                    }
                  />
                  {label}
                </label>
                {hours ? (
                  <>
                    <input
                      type="time"
                      className="rounded-lg border border-slate-300 px-2 py-1 text-base"
                      value={hours.open}
                      onChange={(e) => setDayHours(key, { ...hours, open: e.target.value })}
                    />
                    <span className="text-slate-400">to</span>
                    <input
                      type="time"
                      className="rounded-lg border border-slate-300 px-2 py-1 text-base"
                      value={hours.close}
                      onChange={(e) => setDayHours(key, { ...hours, close: e.target.value })}
                    />
                  </>
                ) : (
                  <span className="text-base text-slate-400">Closed</span>
                )}
              </div>
            )
          })}
          <Button
            size="sm"
            loading={businessHoursMut.isPending}
            onClick={() => businessHoursMut.mutate(businessHours)}
          >
            Save business hours
          </Button>
          {businessHoursMut.isSuccess && <p className="text-base text-green-600">Business hours saved!</p>}
        </div>
      </Card>
    </div>
  )
}
