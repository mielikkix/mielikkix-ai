// Sidene for spørsmål og produkter (norsk bokmål).
import type * as en from '../en/catalog'
import type { DeepPartial } from '../../core'

export const faqs: DeepPartial<typeof en.faqs> = {
  title: 'Vanlige spørsmål',
  subtitle: 'Administrer spørsmålene og svarene chatboten bruker.',
  add: 'Legg til spørsmål',
  newTitle: 'Nytt spørsmål',
  question: 'Spørsmål',
  answer: 'Svar',
  category: 'Kategori (valgfritt)',
  categoryPlaceholder: 'Kategori',
  saveFailed: 'Kunne ikke lagre spørsmålet.',
  empty: 'Ingen spørsmål ennå. Legg til det første ovenfor.',
  editLabel: 'Rediger spørsmålet',
  deleteLabel: 'Slett spørsmålet',
}

export const products: DeepPartial<typeof en.products> = {
  title: 'Produkter og tjenester',
  subtitle: 'Hjelp chatboten med å svare på spørsmål om produktene dine.',
  add: 'Legg til',
  usage: 'Produkter i katalogen',
  newTitle: 'Nytt produkt / ny tjeneste',
  name: 'Navn',
  description: 'Beskrivelse',
  price: 'Pris',
  currency: 'Valuta',
  currencyLocked: 'Oppgrader planen for å prise produkter i andre valutaer.',
  category: 'Kategori',
  saveFailed: 'Kunne ikke lagre produktet.',
  empty: 'Ingen produkter ennå.',
  editLabel: 'Rediger produktet',
  deleteLabel: 'Slett produktet',
}
