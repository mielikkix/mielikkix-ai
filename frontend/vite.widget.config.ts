import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  define: {
    'process.env.NODE_ENV': JSON.stringify('production'),
  },
  build: {
    outDir: 'dist/widget',
    lib: {
      entry: 'src/widget/widget-main.tsx',
      name: 'MielikkiXWidget',
      formats: ['iife'],
    },
    rollupOptions: {
      external: [],
      output: {
        globals: {},
        inlineDynamicImports: true,
        // Vite's lib mode appends the format (".iife.js") to a string
        // fileName; entryFileNames overrides that so the emitted file stays
        // "widget.js", matching the embed snippet and build:widget's copy step.
        entryFileNames: 'widget.js',
      },
    },
  },
})
