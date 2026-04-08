/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'neural': {
          'bg': '#0a0e17',
          'card': '#1a2235',
          'card-hover': '#1f2a42',
          'border': '#2a3548',
        },
        'accent': {
          'cyan': '#00d4ff',
          'purple': '#a855f7',
          'pink': '#ec4899',
          'green': '#22c55e',
          'orange': '#f97316',
          'yellow': '#eab308',
        }
      },
      fontFamily: {
        'space': ['Space Grotesk', 'system-ui', 'sans-serif'],
        'chinese': ['Noto Sans SC', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        'glow-cyan': '0 0 20px rgba(0, 212, 255, 0.3)',
        'glow-purple': '0 0 20px rgba(168, 85, 247, 0.3)',
      },
      animation: {
        'pulse-glow': 'pulse-glow 2s ease-in-out infinite',
        'float': 'float 6s ease-in-out infinite',
      }
    },
  },
  plugins: [],
}
