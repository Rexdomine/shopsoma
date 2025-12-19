/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Shopsoma Brand Palette
        shopsoma: {
          bone: '#E3DCCE',
          dun: '#D2BFA7',
          ecru: '#AFA059',
          brunswick: '#105E53',
          giants: '#F15A26',
          coyote: '#886B4A',
          eerie: '#222424',
        },
        primary: '#105E53', // Brunswick Green (brand core)
        'primary-dark': '#0b4a45',
        'primary-light': '#1a756a',
        cta: '#F15A26', // Giants Orange (CTA)
        'cta-dark': '#d84f20',
        dark: '#222424', // Eerie Black
        light: '#F0F5F4', // Bone / page background
      },
      fontFamily: {
        display: ['"Coconat"', '"Times New Roman"', 'serif'],
        serif: ['"Newsreader 6pt"', 'Georgia', 'serif'],
        body: ['"Newsreader 6pt"', 'Georgia', 'serif'],
        ui: ['"Lexend Tera"', 'system-ui', 'sans-serif'],
        sans: ['"Lexend Tera"', 'system-ui', 'sans-serif'],
      },
      keyframes: {
        'slide-in-right': {
          '0%': { transform: 'translateX(100%)', opacity: '0' },
          '100%': { transform: 'translateX(0)', opacity: '1' },
        },
      },
      animation: {
        'slide-in-right': 'slide-in-right 0.3s ease-out',
      },
    },
  },
  plugins: [],
}
