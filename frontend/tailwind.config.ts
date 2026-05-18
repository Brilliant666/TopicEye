import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: "#FF6B35",
        "primary-hover": "#E85D2A",
        "primary-light": "#FFF4EE",
        "primary-border": "#FFD0B5",
        teal: "#00C9A7",
        "teal-hover": "#00B396",
        "teal-light": "#E6FAF5",
        "teal-border": "#A7F0DB",
        purple: "#8B5CF6",
        "purple-light": "#F0EBFF",
        "purple-border": "#C4B5FD",
        amber: "#D97706",
        "amber-light": "#FEF3C7",
        "amber-border": "#FCD34D",
        surface: "#F7F7F8",
      },
      fontFamily: {
        sans: ['"DM Sans"', "-apple-system", '"PingFang SC"', '"Hiragino Sans GB"', '"Microsoft YaHei"', "sans-serif"],
        mono: ['"DM Mono"', "ui-monospace", "monospace"],
      },
      borderRadius: {
        lg: "12px",
        md: "8px",
        sm: "6px",
      },
      keyframes: {
        "radar-ping": {
          "0%": { transform: "scale(1)", opacity: "0.6" },
          "100%": { transform: "scale(2.8)", opacity: "0" },
        },
        "fade-in": {
          from: { opacity: "0", transform: "translateY(8px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "radar-ping": "radar-ping 2s cubic-bezier(0, 0, 0.2, 1) infinite",
        "fade-in": "fade-in 0.3s ease-out",
      },
    },
  },
  plugins: [],
};

export default config;
