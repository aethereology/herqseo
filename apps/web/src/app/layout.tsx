import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "QueryClear",
  description: "Autonomous SEO/AEO/GEO operator control plane"
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
