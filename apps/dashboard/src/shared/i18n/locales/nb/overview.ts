// Oversikt (forsiden i dashbordet) — norsk bokmål.
import type * as en from '../en/overview'
import type { DeepPartial } from '../../core'

export const overview: DeepPartial<typeof en.overview> = {
  fallbackTitle: 'Oversikt',
  welcome: 'Velkommen tilbake! Her er chatboten din i korte trekk.',
  stats: {
    conversations: 'Samtaler',
    leads: 'Leads fanget opp',
    messages: 'Meldinger fra besøkende',
  },
  usageLabel: 'AI-samtaler denne måneden ({plan}-planen)',
  planLink: 'Plan og forbruk',
  topQuestions: 'Vanligste spørsmål fra besøkende',
  topQuestionsLocked: 'Oversikt over spørsmål er tilgjengelig fra Basic-planen og oppover.',
  upgrade: 'Oppgrader',
  chats: { one: '{count} samtale', other: '{count} samtaler' },
  byIntent: 'Samtaler etter formål',
  intentConversations: { one: 'samtale', other: 'samtaler' },
  intents: {
    faq: 'Spørsmål',
    lead: 'Kontaktforespørsler',
    booking: 'Bestillinger',
    product_inquiry: 'Spørsmål om produkt og pris',
    support: 'Kundestøtte',
  },
  embed: {
    title: 'Legg chatboten inn på nettsiden',
    introBefore: 'Kopier denne koden og lim den inn før ',
    introAfter: ' på nettsiden din.',
    copy: 'Kopier til utklippstavlen',
    privacyTitle: 'Personvern på nettsiden din',
    cookiesBefore: 'Widgeten setter ingen informasjonskapsler. Når en besøkende åpner chatten, lagres en økt-ID (',
    cookiesMiddle: ') og samtalen så langt (',
    cookiesAfter:
      ', slik at den følger med fra side til side) i sessionStorage, som tømmes når fanen lukkes. Nevn dem i erklæringen om informasjonskapsler og personvern.',
    aiNotice: 'Besøkende får beskjed om at de chatter med en AI-assistent, med en lenke til personvernerklæringen din.',
    settingsBefore: 'Legg inn lenken til personvernerklæringen og hvor lenge samtaler skal lagres under ',
    settingsLink: 'Innstillinger → Avansert',
    settingsAfter: '.',
  },
}
