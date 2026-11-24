import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      boxShadow: {
        card: "0 1px 2px rgba(16,24,40,.05), 0 4px 16px -4px rgba(16,24,40,.08)",
        lift: "0 8px 30px -8px rgba(79,70,229,.35)",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
      },
      colors: {
        brand: {
          50: "#eef2ff", 100: "#e0e7ff", 200: "#c7d2fe", 300: "#a5b4fc", 400: "#818cf8",
          500: "#6366f1", 600: "#4f46e5", 700: "#4338ca", 800: "#3730a3", 900: "#312e81",
        },
        gara: {
          pubblicata: "#2563eb",
          pre: "#d97706",
          esito: "#16a34a",
          rettifica: "#9333ea",
          debole: "#6b7280",
        },
        prio: {
          p1: "#dc2626",
          p2: "#ea580c",
          p3: "#ca8a04",
          p4: "#475569",
        },
      },
    },
  },
  plugins: [],
};

export default config;
