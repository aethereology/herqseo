import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#17201b",
        moss: "#60715b",
        lime: "#d7f267",
        paper: "#f8f7f1",
        line: "#d9ded3"
      }
    }
  },
  plugins: []
};

export default config;
