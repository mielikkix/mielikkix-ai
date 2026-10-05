// Samtaler og leads (norsk bokmål).
import type * as en from '../en/inbox'
import type { DeepPartial } from '../../core'

export const conversations: DeepPartial<typeof en.conversations> = {
  title: 'Samtaler',
  subtitle: 'Alle chatøkter med de besøkende på nettsiden din.',
  historyLimit:
    'Viser samtaler fra de siste {days} dagene — det er historikkgrensen i planen din. Eldre samtaler er ikke slettet, bare skjult til du oppgraderer.',
  upgrade: 'Oppgrader',
  searchPlaceholder: 'Søk i det besøkende og chatboten har skrevet',
  searchLabel: 'Søk i samtaler',
  filterLabel: 'Filtrer etter status',
  filters: { all: 'Alle', open: 'Åpne', closed: 'Lukkede' },
  status: { open: 'Åpen', idle: 'Inaktiv', closed: 'Lukket' },
  session: 'Økt {id}…',
  messages: { one: '{count} melding', other: '{count} meldinger' },
  reopen: 'Gjenåpne',
  close: 'Lukk',
  markDone: 'Merk som ferdig',
  delete: 'Slett samtalen',
  deleteConfirm: 'Vil du slette denne samtalen? Dette kan ikke angres.',
  noMatch: 'Ingen samtaler passer til søket.',
  empty: 'Ingen samtaler ennå. De dukker opp her så snart en kunde skriver i widgeten — gå aldri glipp av en kunde.',
}

export const leads: DeepPartial<typeof en.leads> = {
  title: 'Leads',
  subtitle: 'Kontakter som chatboten og nettsiden har fanget opp.',
  exportCsv: 'Eksporter CSV',
  searchPlaceholder: 'Søk på navn, e-post, telefon, bedrift eller notater',
  searchLabel: 'Søk i leads',
  filterLabel: 'Filtrer etter status',
  all: 'Alle',
  statuses: {
    new: 'Ny',
    DEMO_REQUESTED: 'Demo forespurt',
    contacted: 'Kontaktet',
    won: 'Vunnet',
    lost: 'Tapt',
  },
  interestedIn: 'Interessert i: {interest}',
  created: 'Opprettet {date}',
  updated: 'Sist oppdatert {date}',
  status: 'Status',
  notes: 'Notater',
  notesPlaceholder: 'Legg til et notat (lagres når du klikker et annet sted)',
  notesSaving: 'Lagrer …',
  notesFailed: 'Kunne ikke lagre notatet. Prøv igjen.',
  erase: 'Slett personens data',
  eraseConfirm:
    'Vil du slette alle data om {name}? Dette sletter denne leaden, andre leads med samme e-post eller telefon, og chatsamtalene deres. Det kan ikke angres.',
  empty: 'Ingen leads ennå. De dukker opp her når besøkende tar kontakt — gå aldri glipp av en kunde.',
  noMatch: 'Ingen leads passer til søket.',
  csv: {
    name: 'Navn',
    email: 'E-post',
    phone: 'Telefon',
    company: 'Bedrift',
    status: 'Status',
    interest: 'Interesse',
    source: 'Kilde',
    message: 'Melding',
    notes: 'Notater',
    created: 'Opprettet',
    updated: 'Sist oppdatert',
  },
}
