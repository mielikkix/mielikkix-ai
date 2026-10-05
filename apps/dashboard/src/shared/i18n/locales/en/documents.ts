// Documents page (English).

export const documents = {
  title: 'Documents',
  subtitle: 'Upload PDF, Word, Excel, CSV, or TXT files to train your chatbot.',
  upload: 'Upload',
  usage: 'Document uploads',
  uploadFailed: 'Could not upload that file.',
  page: {
    title: 'Fetch from a web page',
    intro:
      "Import the text content of a single page from your website (e.g. an About or FAQ page) directly into your chatbot's knowledge base.",
    placeholder: 'https://your-site.com/about',
    label: 'Web page address',
    fetch: 'Fetch',
    failed: 'Could not fetch that URL.',
  },
  site: {
    title: 'Import your whole website',
    intro:
      "Enter your website's domain and every page we can find will be imported automatically — no need to paste each one in by hand. This runs in the background, so pages appear below as they're processed.",
    placeholder: 'https://your-site.com',
    label: 'Website address',
    import: 'Import site',
    excludePlaceholder: 'Leave out pages containing… e.g. /privacy, /terms, /blog/ (optional, comma-separated)',
    excludeLabel: 'Pages to leave out',
    failed: 'Could not import that website.',
    started: {
      one: "Importing {count} page from your website. It'll appear below as soon as it's processed.",
      other: "Importing {count} pages from your website. They'll appear below as they're processed.",
    },
  },
  status: { embedded: 'Ready', processing: 'Processing', failed: 'Failed' },
  added: 'added {date}',
  chars: '{count} characters',
  charsK: '{count}k characters',
  refetch: 'Re-fetch',
  refetchTitle: 'Fetch this page again',
  refetchFailed: "Couldn't fetch that page again. Check that it's still online.",
  delete: 'Delete document',
  deleteConfirm: 'Remove "{name}" from your chatbot\'s knowledge?',
  empty: 'No documents uploaded yet.',
}
