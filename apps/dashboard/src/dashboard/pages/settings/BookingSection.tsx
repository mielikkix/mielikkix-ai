import { UseMutationResult } from '@tanstack/react-query'
import { Card } from '../../../shared/components/Card'
import { Button } from '../../../shared/components/Button'
import { AgentGate } from '../../../shared/components/AgentGate'
import { api } from '../../../shared/api/client'
import { BusinessHours, CalendarStatus, DayHours, DAYS } from './types'
import { useT } from '../../../shared/i18n'

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
  const { t } = useT()
  // Gated as one whole section, not per-card: Business Hours only ever
  // means anything once Booking Assistant itself is unlocked, so a Free/
  // Basic business must never be able to fill it in and see "saved!" for
  // a feature they can't actually use yet -- that's confusing, not just
  // cosmetically inconsistent with the Booking Calendar card's own lock.
  if (!bookingEnabled) {
    return (
      <Card title={t('settings.booking.agentTitle')}>
        <AgentGate agentKey="booking_assistant">
          <span />
        </AgentGate>
      </Card>
    )
  }

  return (
    <div className="space-y-6">
      <Card title={t('settings.booking.calendarTitle')}>
        <div className="space-y-3">
          {calendarBanner === 'connected' && (
            <p role="status" className="text-base text-green-600">{t('settings.booking.connected')}</p>
          )}
          {calendarBanner === 'error' && (
            <p role="alert" className="text-base text-red-600">{t('settings.booking.connectFailed')}</p>
          )}
          {calendarStatus?.connected ? (
            <>
              <p className="text-base text-slate-700">
                {calendarStatus.google_account_email
                  ? t('settings.booking.connectedAs', { email: calendarStatus.google_account_email })
                  : t('settings.booking.connectedPlain')}
              </p>
              <Button
                variant="secondary"
                loading={disconnectCalendarMut.isPending}
                onClick={() => disconnectCalendarMut.mutate()}
              >
                {t('settings.booking.disconnect')}
              </Button>
            </>
          ) : (
            <>
              <p className="text-sm text-slate-500">{t('settings.booking.connectHelp')}</p>
              <Button
                onClick={() => {
                  window.location.href = `${api.defaults.baseURL}/businesses/me/calendar/authorize`
                }}
              >
                {t('settings.booking.connect')}
              </Button>
            </>
          )}
        </div>
      </Card>

      <Card title={t('settings.booking.hoursTitle')}>
        <div className="space-y-3">
          <p className="text-sm text-slate-500">{t('settings.booking.hoursHelp')}</p>
          {DAYS.map((key) => {
            const label = t(`settings.booking.days.${key}`)
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
                      aria-label={t('settings.booking.opensAt', { day: label })}
                      className="rounded-lg border border-slate-300 px-2 py-1 text-base"
                      value={hours.open}
                      onChange={(e) => setDayHours(key, { ...hours, open: e.target.value })}
                    />
                    <span className="text-slate-400">{t('settings.booking.to')}</span>
                    <input
                      type="time"
                      aria-label={t('settings.booking.closesAt', { day: label })}
                      className="rounded-lg border border-slate-300 px-2 py-1 text-base"
                      value={hours.close}
                      onChange={(e) => setDayHours(key, { ...hours, close: e.target.value })}
                    />
                  </>
                ) : (
                  <span className="text-base text-slate-400">{t('settings.booking.closed')}</span>
                )}
              </div>
            )
          })}
          <Button
            size="sm"
            loading={businessHoursMut.isPending}
            onClick={() => businessHoursMut.mutate(businessHours)}
          >
            {t('settings.booking.saveHours')}
          </Button>
          {businessHoursMut.isSuccess && <p role="status" className="text-base text-green-600">{t('settings.booking.hoursSaved')}</p>}
        </div>
      </Card>
    </div>
  )
}
