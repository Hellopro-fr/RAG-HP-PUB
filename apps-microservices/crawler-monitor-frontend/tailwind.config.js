/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ['class'],
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    container: {
      center: true,
      padding: '1rem',
      screens: { '2xl': '1400px' },
    },
    extend: {
      colors: {
        border:     'var(--border)',
        input:      'var(--input)',
        ring:       'var(--ring)',
        background: 'var(--background)',
        foreground: 'var(--foreground)',
        primary: {
          DEFAULT:    'var(--primary)',
          foreground: 'var(--primary-foreground)',
        },
        secondary: {
          DEFAULT:    'var(--secondary)',
          foreground: 'var(--secondary-foreground)',
        },
        destructive: {
          DEFAULT:    'var(--destructive)',
          foreground: 'var(--destructive-foreground)',
        },
        muted: {
          DEFAULT:    'var(--muted)',
          foreground: 'var(--muted-foreground)',
        },
        accent: {
          DEFAULT:    'var(--accent)',
          soft:       'var(--accent-soft)',
          ink:        'var(--accent-ink)',
          foreground: 'var(--accent-foreground)',
        },
        popover: {
          DEFAULT:    'var(--popover)',
          foreground: 'var(--popover-foreground)',
        },
        card: {
          DEFAULT:    'var(--card)',
          foreground: 'var(--card-foreground)',
        },
        // Semantic severity — used by badges / alerts / charts
        success: {
          DEFAULT:    'var(--success)',
          foreground: 'var(--success-foreground)',
        },
        warning: {
          DEFAULT:    'var(--warning)',
          foreground: 'var(--warning-foreground)',
        },
        info: {
          DEFAULT:    'var(--info)',
          soft:       'var(--info-soft)',
          foreground: 'var(--info-foreground)',
        },
        // Design system tokens oklch
        bg: {
          0: 'var(--bg-0)',
          1: 'var(--bg-1)',
          2: 'var(--bg-2)',
        },
        surface: 'var(--surface)',
        ink: {
          0: 'var(--ink-0)',
          1: 'var(--ink-1)',
          2: 'var(--ink-2)',
          3: 'var(--ink-3)',
        },
        hairline: {
          DEFAULT: 'var(--hairline)',
          strong:  'var(--hairline-strong)',
        },
        ok:   { DEFAULT: 'var(--ok)',   soft: 'var(--ok-soft)'   },
        warn: { DEFAULT: 'var(--warn)', soft: 'var(--warn-soft)' },
        err:  { DEFAULT: 'var(--err)',  soft: 'var(--err-soft)'  },
      },
      borderRadius: {
        lg:    '12px',
        md:    '8px',
        sm:    '6px',
        xl:    '16px',
        '2xl': '20px',
        full:  '9999px',
        DEFAULT: '8px',
      },
      fontFamily: {
        sans:    ['Inter', 'system-ui', 'sans-serif'],
        display: ['Inter Tight', 'Inter', 'sans-serif'],
        mono:    ['JetBrains Mono', 'monospace'],
      },
      boxShadow: {
        sm: 'var(--shadow-sm)',
        md: 'var(--shadow-md)',
      },
      keyframes: {
        'accordion-down': {
          from: { height: '0' },
          to: { height: 'var(--radix-accordion-content-height)' },
        },
        'accordion-up': {
          from: { height: 'var(--radix-accordion-content-height)' },
          to: { height: '0' },
        },
      },
      animation: {
        'accordion-down': 'accordion-down 0.2s ease-out',
        'accordion-up': 'accordion-up 0.2s ease-out',
      },
    },
  },
  plugins: [require('tailwindcss-animate')],
};
