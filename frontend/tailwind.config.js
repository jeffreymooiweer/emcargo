/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: { extend: { colors: {
    slate: { 50: "#f7f8fa", 100: "#eef0f4", 200: "#dce0e7", 300: "#c3cad5", 400: "#9aa5b5", 500: "#6e7a8d", 600: "#526075", 700: "#353f4e", 800: "#272f3b", 900: "#191f29", 950: "#10151d" },
    brand: { 50: "#f0f5ff", 100: "#e0eaff", 200: "#c3d6ff", 300: "#a6c3ff", 400: "#80a9ff", 500: "#5b8ef6", 600: "#376be0", 700: "#2955bb", 800: "#25488d", 900: "#203b6d", 950: "#182642" }
  }}},
  plugins: [],
};
