import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
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
