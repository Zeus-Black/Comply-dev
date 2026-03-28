import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Comply — Assistant IA des Junior-Entreprises",
  description: "L'assistant intelligent de la CNJE pour les JE françaises.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr">
      <body>{children}</body>
    </html>
  );
}
