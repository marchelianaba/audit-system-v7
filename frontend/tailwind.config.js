/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        // INTEGRAL AI Workspace palette (8 Juni 2026 — rebrand fr SIMWAS v2 visual)
        // Primary: violet INTEGRAL #5C4FE7 (sama dgn SIMWAS supaya familiar)
        // Tetap kasih "dark" variant untuk hover/active states
        primary: {
          DEFAULT: '#5C4FE7',
          dark: '#4338CA',
          light: '#A78BFA',
          50: '#F5F3FF',
          100: '#EDE9FE',
          200: '#DDD6FE',
          300: '#C4B5FD',
          400: '#A78BFA',
          500: '#8B5CF6',
          600: '#7C3AED',
          700: '#6D28D9',
          800: '#5B21B6',
          900: '#4C1D95',
        },
        accent: '#F59E0B',
        // Role colors — tetap pakai konvensi v7 supaya UI panel role-aware konsisten
        at: '#2563EB',       // biru
        kt: '#9333EA',       // ungu lebih gelap
        pt: '#DB2777',       // pink
        pm: '#7C3AED',       // violet tua
        qc: '#16A34A',       // hijau success
        // INTEGRAL-specific
        ink: '#1a1a2e',       // text gelap
        surface: '#F9FAFB',   // light bg
        muted: '#6B7280',     // gray text
      },
      fontFamily: {
        sans: ['var(--font-inter)', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        'integral': '0 4px 12px -2px rgba(92, 79, 231, 0.15)',
        'card': '0 1px 3px rgba(0, 0, 0, 0.06)',
      },
    },
  },
  plugins: [],
};
