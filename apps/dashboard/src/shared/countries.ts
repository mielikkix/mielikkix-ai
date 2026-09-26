// ISO 3166-1 alpha-2 codes accepted by the API for the Register form's Country
// field -- keep in sync with apps/api/app/core/countries.py. Display names
// come from the browser (Intl.DisplayNames) rather than a hand-kept list.
const COUNTRY_CODES = `
  AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS
  BT BV BW BY BZ CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE
  EG EH ER ES ET FI FJ FK FM FO FR GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM
  HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO JP KE KG KH KI KM KN KP KR KW KY KZ LA LB LC
  LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW MX MY MZ NA
  NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PW PY QA RE RO RS RU RW
  SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO
  TR TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI VN VU WF WS YE YT ZA ZM ZW
`.trim().split(/\s+/)

export interface Country {
  code: string
  name: string
}

export function countryOptions(locale = 'en'): Country[] {
  let names: Intl.DisplayNames | null = null
  try {
    names = new Intl.DisplayNames([locale], { type: 'region' })
  } catch {
    // Very old browsers: fall back to showing the code itself.
  }
  return COUNTRY_CODES.map((code) => ({ code, name: names?.of(code) ?? code })).sort((a, b) =>
    a.name.localeCompare(b.name, locale),
  )
}

/** Country from the browser's locale (e.g. "nb-NO" -> "NO"), or '' if it has no supported region. */
export function guessCountry(): string {
  const tags = typeof navigator === 'undefined' ? [] : [...(navigator.languages ?? []), navigator.language]
  // An explicit region anywhere in the list ("en-GB") beats a guessed one
  // ("en" maximizes to US), so check all explicit ones first.
  for (const maximize of [false, true]) {
    for (const tag of tags) {
      try {
        const locale = new Intl.Locale(tag)
        const region = (maximize ? locale.maximize() : locale).region
        if (region && COUNTRY_CODES.includes(region)) return region
      } catch {
        // ignore malformed tags
      }
    }
  }
  return ''
}
