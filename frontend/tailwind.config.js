/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        slate: { 50: "#f5f7fb", 100: "#eaf0f8", 200: "#d7e1ee", 300: "#b8c9df", 400: "#92a8c5", 500: "#647c9c", 600: "#48617f", 700: "#2a405e", 800: "#1c2d45", 900: "#101d31", 950: "#070f1e" },
        /**
         * The brand blue, complete.
         *
         * Five shades were defined and eleven were used. Tailwind generates
         * nothing for a shade that does not exist, so twenty-nine classes
         * across ten files were silently doing nothing — and the ones that
         * mattered most were the dark-mode backgrounds: a selected option
         * carried `bg-brand-50` for the light theme and
         * `dark:bg-brand-950/40` to override it in the dark one. With 950
         * missing, the override never existed, so a selected button stayed
         * near-white in the dark theme while its text went to `brand-100`.
         * White on near-white: the selected option was the one you could not
         * read.
         *
         * The five original values are untouched; only the gaps are filled,
         * so nothing that already rendered changes shade. From 500 onwards
         * the ramp runs one step darker than Tailwind's own blue, which is
         * what the original values were, and 800-950 continue it into the
         * navies the dark theme needs.
         */
        brand: {
          50: "#f0f7ff",
          100: "#dceeff",
          200: "#bcdcff",
          300: "#8ec2fd",
          400: "#5b9cf8",
          500: "#2875ff",
          600: "#165dfa",
          700: "#164bcc",
          800: "#1e3a8a",
          900: "#172554",
          950: "#0f1836",
        },
      },
    },
  },
  plugins: [],
};
