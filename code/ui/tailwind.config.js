/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#07070B", bone: "#EDE9E0", panel: "#0F0F16", line: "#34344A", muted: "#B8B4C6",
        proven: "#7CFFB2", haunted: "#FF6B47", flow: "#B3A8FF", na: "#A3A0B0",
      },
      fontFamily: {
        display: ['"Instrument Serif"', "Georgia", "serif"],
        sans: ['"Inter Variable"', "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono Variable"', "ui-monospace", "monospace"],
      },
      borderRadius: { panel: "12px" },
    },
  },
  plugins: [],
};
