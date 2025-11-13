/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Shop Soma Brand Colors
        primary: '#105E53',
        'primary-dark': '#0d4a41',
        'primary-light': '#1a756a',
        dark: '#454444',
        light: '#B0B0B0',
        // Keep existing teal colors for backwards compatibility
        teal: {
          50: '#f0fdfa',
          100: '#ccfbf1',
          200: '#99f6e4',
          300: '#5eead4',
          400: '#2dd4bf',
          500: '#14b8a6',
          600: '#0d9488',
          700: '#105E53',
          800: '#0d4a41',
          900: '#134e4a',
        },
      },
      fontFamily: {
        display: ['"Lao MN"', 'serif'],
        body: ['Montserrat', 'sans-serif'],
        sans: ['Montserrat', 'ui-sans-serif', 'system-ui'],
      },
    },
  },
  plugins: [],
}
