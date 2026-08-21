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

/** Exchange rates change slowly enough that once/day is plenty — keeps API calls low. */
const RATE_STALE_TIME = 24 * 60 * 60 * 1000

export function useCurrency() {
  const [currency, setCurrencyState] = useState<CurrencyCode>(getStoredCurrency)

  const { data: rate } = useQuery({
    queryKey: ['exchange-rate', currency],
    queryFn: () => fetchExchangeRate(currency),
    staleTime: RATE_STALE_TIME,
    enabled: currency !== BASE_CURRENCY,
  })

  const setCurrency = useCallback((next: CurrencyCode) => {
    setStoredCurrency(next)
    setCurrencyState(next)
  }, [])

  // No rate yet (cold cache, API down) — show USD rather than a wrong/stale amount.
  const format = useCallback(
    (usdAmount: number) => {
      if (currency === BASE_CURRENCY) return formatCurrency(usdAmount, BASE_CURRENCY)
      if (rate == null) return formatCurrency(usdAmount, BASE_CURRENCY)
      return formatCurrency(Math.round(usdAmount * rate), currency)
    },
    [currency, rate]
  )

  return { currency, setCurrency, format }
}
