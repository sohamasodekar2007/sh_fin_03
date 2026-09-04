import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CloudCare — AI-Powered Cloud Cost Optimization",
  description:
    "CloudCare watches your AWS infrastructure around the clock, flags waste with evidence, and only acts with safety guardrails and human approval.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="font-body antialiased">{children}</body>
    </html>
  );
}
