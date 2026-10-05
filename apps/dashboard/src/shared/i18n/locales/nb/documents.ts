// Dokumenter (norsk bokmål).
import type * as en from '../en/documents'
import type { DeepPartial } from '../../core'

export const documents: DeepPartial<typeof en.documents> = {
  title: 'Dokumenter',
  subtitle: 'Last opp PDF-, Word-, Excel-, CSV- eller TXT-filer for å lære opp chatboten.',
  upload: 'Last opp',
  usage: 'Opplastede dokumenter',
  uploadFailed: 'Kunne ikke laste opp filen.',
  page: {
    title: 'Hent fra en nettside',
    intro:
      'Importer teksten fra én side på nettstedet ditt (f.eks. en Om oss- eller FAQ-side) rett inn i kunnskapsbasen til chatboten.',
    placeholder: 'https://dinbedrift.no/om-oss',
    label: 'Adressen til nettsiden',
    fetch: 'Hent',
    failed: 'Kunne ikke hente den adressen.',
  },
  site: {
    title: 'Importer hele nettstedet',
    intro:
      'Skriv inn domenet til nettstedet ditt, så importeres alle sidene vi finner automatisk — du slipper å lime inn hver enkelt. Dette skjer i bakgrunnen, og sidene dukker opp nedenfor etter hvert som de behandles.',
    placeholder: 'https://dinbedrift.no',
    label: 'Adressen til nettstedet',
    import: 'Importer nettstedet',
    excludePlaceholder: 'Hopp over sider som inneholder … f.eks. /personvern, /vilkar, /blogg/ (valgfritt, kommaseparert)',
    excludeLabel: 'Sider som skal hoppes over',
    failed: 'Kunne ikke importere det nettstedet.',
    started: {
      one: 'Importerer {count} side fra nettstedet ditt. Den dukker opp nedenfor så snart den er behandlet.',
      other: 'Importerer {count} sider fra nettstedet ditt. De dukker opp nedenfor etter hvert som de behandles.',
    },
  },
  status: { embedded: 'Klar', processing: 'Behandles', failed: 'Feilet' },
  added: 'lagt til {date}',
  chars: '{count} tegn',
  charsK: '{count}k tegn',
  refetch: 'Hent på nytt',
  refetchTitle: 'Hent denne siden på nytt',
  refetchFailed: 'Kunne ikke hente siden på nytt. Sjekk at den fortsatt er tilgjengelig.',
  delete: 'Slett dokumentet',
  deleteConfirm: 'Vil du fjerne «{name}» fra kunnskapen til chatboten?',
  empty: 'Ingen dokumenter lastet opp ennå.',
}
