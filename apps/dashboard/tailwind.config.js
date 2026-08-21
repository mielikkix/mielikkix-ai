/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Royal Orange (primary)
        brand: {
          50: '#fff8f2',
          100: '#fff0e6',
          200: '#ffdabf',
          300: '#ffc499',
          400: '#ff974c',
          500: '#ff6b00',
          600: '#e05e00',
          700: '#b84d00',
          800: '#943e00',
          900: '#6b2d00',
        },
        // Warm Gold (secondary)
        gold: {
          50: '#fefbf4',
          100: '#fef6e9',
          200: '#fce9c8',
          300: '#fbdba7',
          400: '#f8c165',
          500: '#f5a623',
          600: '#d8921f',
          700: '#b07819',
          800: '#8e6014',
          900: '#67460f',
        },
        // Deep Charcoal / Soft Cream neutral ramp
        slate: {
          50: '#fff8f0',
          100: '#efe8e1',
          200: '#d8d2cc',
          300: '#bdb8b2',
          400: '#9d9994',
          500: '#7c7976',
          600: '#615f5c',
          700: '#4a4947',
          800: '#333232',
          900: '#1a1a1a',
        },
      },
      fontFamily: {
        sans: [
          'Colfax',
          'colfax-web',
          'Proxima Nova',
          'Open Sans',
          'Gill Sans MT',
          'Gill Sans',
          'Corbel',
          'Arial',
          'sans-serif',
        ],
      },
    },
  },
  plugins: [],
}
