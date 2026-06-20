// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Nimesh Cheedella

import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: "Heisenberg",
  description: "Quantum programming in your browser.",
  authors: [{ name: "Nimesh Cheedella", url: "mailto:chnimesh0808@gmail.com" }],
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-background text-foreground antialiased">{children}</body>
    </html>
  );
}
