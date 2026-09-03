import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: "#F6F9FB",
        surface: "#FFFFFF",
        surfaceAlt: "#EAF2F6",
        surfaceAlt2: "#DCEEEA",
        ink: "#10222E",
        inkSoft: "#52697C",
        inkFaint: "#8CA0AE",
        line: "#DCE7EC",
        brandBlue: "#2F6690",
        brandBlueDeep: "#1D4A6B",
        brandTeal: "#3FA796",
        brandAmber: "#E2A93B",
      },
      fontFamily: {
        display: ["Space Grotesk", "sans-serif"],
        body: ["Inter", "sans-serif"],
        mono: ["IBM Plex Mono", "monospace"],
      },
      boxShadow: {
        soft: "0 10px 30px -14px rgba(16,34,46,0.16)",
        card: "0 4px 18px -6px rgba(16,34,46,0.10)",
      },
      borderRadius: {
        lg2: "22px",
      },
    },
  },
  plugins: [],
};

export default config;
