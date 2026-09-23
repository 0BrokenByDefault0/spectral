import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "VoxChain",
  description: "Analyse a vocal recording and get a plugin chain at every price point",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="mx-auto max-w-6xl px-8 py-10">
          <header className="mb-10 flex items-baseline gap-4">
            <h1 className="text-2xl font-semibold tracking-tight">VoxChain</h1>
            <p className="muted text-sm">
              Upload a vocal, get a chain you can actually build
            </p>
          </header>
          {children}
        </div>
      </body>
    </html>
  );
}
