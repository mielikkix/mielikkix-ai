import { useCallback, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  BASE_CURRENCY,
  CurrencyCode,
  fetchExchangeRate,
  formatCurrency,
  getStoredCurrency,
  setStoredCurrency,
} from '../currency'
import { useT } from '../i18n'

/** Exchange rates change slowly enough that once/day is plenty — keeps API calls low. */
const RATE_STALE_TIME = 24 * 60 * 60 * 1000

export function useCurrency() {
  const { formatNok } = useT()
  const [currency, setCurrencyState] = useState<CurrencyCode>(getStoredCurrency)

  const { data: rate } = useQuery({
    queryKey: ['exchange-rate', BASE_CURRENCY, currency],
    queryFn: () => fetchExchangeRate(currency),
    staleTime: RATE_STALE_TIME,
    enabled: currency !== BASE_CURRENCY,
  })

  const setCurrency = useCallback((next: CurrencyCode) => {
    setStoredCurrency(next)
    setCurrencyState(next)
  }, [])

  // True while prices are shown in EUR/USD -- pages then say they're approximate and billed in NOK.
  const converted = currency !== BASE_CURRENCY && rate != null

  // No rate yet (cold cache, API down) — show NOK rather than a wrong/stale amount.
  const format = useCallback(
    (nokAmount: number) => {
      if (!converted || rate == null) return formatNok(nokAmount)
      return formatCurrency(Math.round(nokAmount * rate), currency)
    },
    [converted, currency, rate, formatNok]
  )

  return { currency, setCurrency, format, converted }
}
