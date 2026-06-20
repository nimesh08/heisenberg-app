// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Nimesh Cheedella

import Link from "next/link";
import { redirect } from "next/navigation";

import { Button } from "@/components/ui/button";
import { auth } from "@/lib/auth";

/**
 * Public landing page (item #13 in the plan). Logged-in users redirect to the
 * shell at /app; logged-out users see the splash + sign-in/up CTAs.
 */
export default async function LandingPage() {
  const session = await auth();
  if (session?.user) {
    redirect("/app");
  }

  return (
    <main className="flex min-h-screen flex-col">
      <header className="border-b border-border">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-4">
          <div className="font-mono text-lg font-bold">Heisenberg</div>
          <nav className="flex items-center gap-4 text-sm">
            <Link href="/privacy" className="text-muted-foreground hover:text-foreground">
              Privacy
            </Link>
            <Link href="/terms" className="text-muted-foreground hover:text-foreground">
              Terms
            </Link>
            <Button asChild variant="outline" size="sm">
              <Link href="/login">Sign in</Link>
            </Button>
            <Button asChild size="sm">
              <Link href="/signup">Sign up</Link>
            </Button>
          </nav>
        </div>
      </header>

      <section className="flex flex-1 flex-col items-center justify-center px-6 py-20 text-center">
        <h1 className="text-4xl font-bold tracking-tight sm:text-6xl">
          Quantum programming in your browser.
        </h1>
        <p className="mt-6 max-w-2xl text-lg text-muted-foreground">
          A real VS Code, three first-class quantum languages, and a one-click path from circuit to
          a live QPU. Bring your own IBM, AWS Braket, or Azure Quantum credentials, or
          pay-as-you-go.
        </p>

        <ul className="mt-10 grid gap-4 text-left sm:grid-cols-3">
          <li className="rounded-lg border border-border bg-card p-4">
            <div className="font-mono text-sm font-bold text-primary">Three languages</div>
            <p className="mt-2 text-sm text-muted-foreground">
              Spinor (.spn), Phonon (.phn), and Photon (.pho) — each with grammar, diagnostics, and
              Bell hello-worlds.
            </p>
          </li>
          <li className="rounded-lg border border-border bg-card p-4">
            <div className="font-mono text-sm font-bold text-primary">BYOK by default</div>
            <p className="mt-2 text-sm text-muted-foreground">
              Paste your provider key once. We encrypt at rest with pgcrypto and never log it.
            </p>
          </li>
          <li className="rounded-lg border border-border bg-card p-4">
            <div className="font-mono text-sm font-bold text-primary">No install</div>
            <p className="mt-2 text-sm text-muted-foreground">
              Real VS Code in the browser, branded Heisenberg IDE. No marketplace, no terminal, no
              surprises.
            </p>
          </li>
        </ul>

        <div className="mt-12 flex gap-4">
          <Button asChild size="lg">
            <Link href="/signup">Get started</Link>
          </Button>
          <Button asChild size="lg" variant="outline">
            <Link href="/login">I have an account</Link>
          </Button>
        </div>
      </section>

      <footer className="border-t border-border px-6 py-6 text-center text-xs text-muted-foreground">
        © 2026 Nimesh Cheedella · Heisenberg v0.1.0 ·{" "}
        <Link href="/privacy" className="hover:text-foreground">
          Privacy
        </Link>{" "}
        ·{" "}
        <Link href="/terms" className="hover:text-foreground">
          Terms
        </Link>
      </footer>
    </main>
  );
}
