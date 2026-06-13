import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Canary - Your Intelligent Voice Companion",
  description: "A warm, intelligent voice assistant that listens, understands, and responds with care. Powered by the Canary AI engine.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">
        {children}
      </body>
    </html>
  );
}
