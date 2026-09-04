import type { Metadata } from "next";
import { Bricolage_Grotesque, Inter_Tight, JetBrains_Mono } from "next/font/google";

import { SessionSync } from "@/components/auth/SessionSync";
import { THEME_BOOTSTRAP } from "@/components/cfo/ThemeToggle";
import { QueryProvider } from "@/components/QueryProvider";
import { Toaster } from "@/components/ui/sonner";

import "./globals.css";

// Wired to the --font-display / --font-sans / --font-mono tokens consumed
// by globals.css's @theme inline block — see that file's module comment.
// The mono font matters more than it looks: every numeral in this design
// (KpiStrip, .num utility) uses tabular figures, which only JetBrains Mono
// (not a system fallback) guarantees here.
const bricolageGrotesque = Bricolage_Grotesque({
  subsets: ["latin"],
  variable: "--font-bricolage-grotesque",
  display: "swap",
});

const interTight = Inter_Tight({
  subsets: ["latin"],
  variable: "--font-inter-tight",
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "CloudCare",
  description: "Multi-cloud FinOps cost-optimization platform.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className={`${bricolageGrotesque.variable} ${interTight.variable} ${jetbrainsMono.variable}`}
      suppressHydrationWarning
    >
      <head>
        {/* Blocking, pre-hydration: applies the saved theme class before
            first paint so there is no flash of the wrong theme. Reading
            localStorage during render instead of here causes a hydration
            mismatch — see src/components/cfo/ThemeToggle.tsx. */}
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOTSTRAP }} />
      </head>
      <body suppressHydrationWarning>
        <QueryProvider>
          <SessionSync>
            {children}
            <Toaster />
          </SessionSync>
        </QueryProvider>
      </body>
    </html>
  );
}
