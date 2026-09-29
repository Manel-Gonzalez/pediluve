import type { Config } from 'tailwindcss'

export default {
  // Scan every component/page for class names — update this if new source
  // file types are added (e.g. .mdx) so their classes aren't purged.
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        // Keep system-ui — no external font load, no extra dependency.
        sans: ['system-ui', 'sans-serif'],
      },
      colors: {
        // "Studio de voz" accent — teal, evokes audio/waveform tooling
        // without the coral option's louder, more playful connotation.
        accent: {
          50: '#effcfa',
          100: '#c8f6ef',
          200: '#92ece0',
          300: '#5cdccc',
          400: '#2ec4b3',
          500: '#17a396', // primary accent
          600: '#12827a',
          700: '#106863',
          800: '#0f5350',
          900: '#0d4542',
        },
        ink: {
          50: '#f7f8f8',
          100: '#eceeee',
          200: '#d5d9da',
          300: '#b1b8ba',
          400: '#858f92',
          500: '#697276',
          600: '#565e61',
          700: '#484e50',
          800: '#3f4445',
          900: '#1a1a1a', // body text
        },
      },
      fontSize: {
        xs: ['0.8rem', { lineHeight: '1.4' }],
        sm: ['0.9rem', { lineHeight: '1.4' }],
        base: ['1rem', { lineHeight: '1.5' }],
        lg: ['1.125rem', { lineHeight: '1.5' }],
        xl: ['1.25rem', { lineHeight: '1.4' }],
        '2xl': ['1.5rem', { lineHeight: '1.3' }],
        '3xl': ['2rem', { lineHeight: '1.2' }],
      },
      fontWeight: {
        normal: '400',
        medium: '500',
        semibold: '600',
        bold: '700',
      },
    },
  },
  plugins: [],
} satisfies Config
