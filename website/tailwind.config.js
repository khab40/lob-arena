/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        arena: {
          ink: "#162033",
          panel: "#ffffff",
          grid: "#dce2ec",
          bid: "#146c38",
          ask: "#8a1f1f",
          accent: "#2457d6"
        }
      }
    }
  },
  plugins: []
};
