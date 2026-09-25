// @ts-check
import { defineConfig } from 'astro/config';

import tailwindcss from '@tailwindcss/vite';

import sitemap from '@astrojs/sitemap';

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

  integrations: [sitemap()]
});