// Gjenbrukbare dashbordkomponenter (norsk bokmål).
import type * as en from '../en/shared'
import type { DeepPartial } from '../../core'

export const gates: DeepPartial<typeof en.gates> = {
  higherPlan: 'Tilgjengelig på en høyere plan.',
  comingSoon: 'Kommer snart.',
  upgrade: 'Oppgrader',
  agentInactive: 'Ikke aktivert på kontoen din ennå.',
  contactUs: 'Kontakt oss',
}

export const usage: DeepPartial<typeof en.usage> = {
  unlimitedOnPlan: '(ubegrenset på planen din)',
  upgradeForMore: 'Oppgrader for mer',
}

export const currency: DeepPartial<typeof en.currency> = {
  label: 'Valuta',
  names: { EUR: 'Euro', USD: 'Amerikanske dollar', NOK: 'Norske kroner' },
}

export const payment: DeepPartial<typeof en.payment> = {
  soonTitle: 'Betaling kommer snart',
  soonBefore: 'Vi kan ikke ta imot kortbetaling ennå, så du kan ikke oppgradere til ',
  soonAfter: '-planen akkurat nå. Vi jobber med saken og gir deg beskjed så snart det er klart.',
  gotIt: 'Skjønner',
}

export const checkout: DeepPartial<typeof en.checkout> = {
  title: 'Oppgrader til {plan}',
  planLine: '{plan}-planen',
  priceExclVat: '{price}/mnd eks. mva.',
  approx: '≈ {price}/mnd',
  cardName: 'Navn på kortet',
  cardNamePlaceholder: 'Kari Nordmann',
  cardNumber: 'Kortnummer',
  expiry: 'Utløpsdato',
  expiryPlaceholder: 'MM/ÅÅ',
  cvc: 'CVC',
  errCardName: 'Skriv inn navnet på kortet',
  errCardDigits: 'Kortnummeret må ha 16 sifre',
  errCardCheck: 'Kortnummeret ser ikke riktig ut',
  errExpiryFormat: 'Skriv utløpsdatoen som MM/ÅÅ',
  errExpiryMonth: 'Skriv inn en gyldig måned',
  errExpired: 'Kortet er utløpt',
  errCvc: 'Skriv inn en gyldig CVC',
  demoNotice:
    'Ingen betalingsløsning er koblet til ennå, så du blir ikke belastet, og kortopplysningene blir aldri sendt eller lagret. Dette bytter bare planen for demoformål.',
  failed: 'Kunne ikke fullføre oppgraderingen. Prøv igjen.',
  pay: 'Betal {price}/mnd og oppgrader',
}

export const knowledge: DeepPartial<typeof en.knowledge> = {
  title: {
    one: '{count} mulig motsigelse i kunnskapen til chatboten',
    other: '{count} mulige motsigelser i kunnskapen til chatboten',
  },
  similarFaqs: 'Disse spørsmålene er nesten like, men har ulike svar. Chatboten kan velge hvilket som helst av dem.',
  priceMismatch: 'Dette produktet står oppført flere ganger med ulik pris. Chatboten kan oppgi hvilken som helst av prisene.',
  noPrice: 'ingen pris',
}

export const testChat: DeepPartial<typeof en.testChat> = {
  title: 'Test chatboten',
  intro: 'Spør om det kundene dine spør om, og sjekk svarene. Testsamtaler teller ikke mot planen og lagres ikke under Samtaler.',
  examples: 'Prøv: «Når har dere åpent?» eller «Hva koster det?»',
  weak: 'Kunnskapsbasen din ser ikke ut til å dekke dette. Legg til et spørsmål med svar eller et dokument, så chatboten kan svare.',
  thinking: 'Tenker …',
  failed: 'Fikk ikke noe svar. Prøv igjen.',
  placeholder: 'Skriv et spørsmål …',
  inputLabel: 'Testspørsmål',
  send: 'Send testspørsmålet',
  reset: 'Start på nytt',
}
