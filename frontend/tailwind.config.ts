import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Reserved status colours, never used for anything but severity. The three
        // severities are all warm and sit close together (warning vs serious measures
        // ΔE 13.6 for normal vision), so badges also differ by fill treatment and
        // always carry the word — severity is never colour alone.
        minor: "#fab219",
        moderate: "#ec835a",
        critical: "#d03b3b",
        good: "#0ca30c",
        // Single chart series; validated for contrast against the panel surface.
        series: "#3987e5",
      },
    },
  },
  plugins: [],
};

export default config;
