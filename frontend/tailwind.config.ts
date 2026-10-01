import type { Config } from 'tailwindcss'

// A semantic color backed by a CSS variable holding "R G B" channels (see
// index.css), so opacity modifiers like `bg-canvas/80` still work.
const token = (name: string) => `rgb(var(--${name}) / <alpha-value>)`

export default {
  // The theme is a `dark` class on <html>, set before first paint by
  // index.html and kept in sync by hooks/useTheme.ts (KAN-74).
  darkMode: 'selector',
  // Scan every component/page for class names — update this if new source
  // file types are added (e.g. .mdx) so their classes aren't purged.
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        // System fonts - no external font load, no extra dependency; SF on
        // Apple devices, Segoe UI on Windows, Roboto on Android.
        sans: ['ui-sans-serif', 'system-ui', '-apple-system', '"Segoe UI"', 'Roboto', 'sans-serif'],
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
          950: '#0b0d0e',
        },
        // Semantic tokens (KAN-74): components use these, never a raw
        // ink/accent step, so light and dark each get one definition in
        // index.css instead of a `dark:` pair on every element.
        canvas: token('canvas'), // page background
        surface: token('surface'), // cards, dialogs, inputs
        subtle: token('subtle'), // hover fills, secondary panels
        line: token('line'), // borders
        'line-strong': token('line-strong'), // hovered/focused borders
        fg: token('fg'), // body text
        muted: token('muted'), // secondary text
        primary: token('primary'), // buttons, links, focus
        'primary-hover': token('primary-hover'),
        'on-primary': token('on-primary'), // text on a primary fill
        highlight: token('highlight'), // soft accent fill (badges, current line)
        'highlight-fg': token('highlight-fg'), // text on a highlight fill
        danger: token('danger'),
        'danger-soft': token('danger-soft'),
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
      keyframes: {
        // Login hero's waveform bars and caption lines (KAN-79).
        wave: {
          '0%, 100%': { transform: 'scaleY(0.35)' },
          '50%': { transform: 'scaleY(1)' },
        },
        'caption-in': {
          from: { opacity: '0', transform: 'translateY(4px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        wave: 'wave 1.2s ease-in-out infinite',
        'caption-in': 'caption-in 300ms ease-out both',
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
