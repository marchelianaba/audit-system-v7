/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        primary: { DEFAULT: '#0B3D91', dark: '#072458' },
        accent: '#F5A623',
        at: '#1565C0',
        kt: '#6A1B9A',
        qc: '#2E7D32',
        ing: '#E65100',
      },
    },
  },
  plugins: [],
};
