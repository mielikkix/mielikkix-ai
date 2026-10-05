// @ts-check
import { defineConfig } from 'astro/config';

import tailwindcss from '@tailwindcss/vite';

import sitemap from '@astrojs/sitemap';

import norwegianPages from './integrations/norwegian-pages.mjs';

// https://astro.build/config
export default defineConfig({
  site: 'https://mielikkix.ai',

  vite: {
    plugins: [tailwindcss()],
    build: {
      // Never inline <script> bundles into the HTML: the CSP (public/.htaccess)
      // has no 'unsafe-inline' for script-src, so an inlined script (e.g. the
      // small cookie-consent one) would silently be blocked in production.
      assetsInlineLimit: 0
    }
  },

  // norwegianPages runs after sitemap on purpose: it adds the /no/ URLs to the
  // sitemap that sitemap() has just written.
  integrations: [sitemap({ filter: (page) => !page.includes('/404') }), norwegianPages()]
});