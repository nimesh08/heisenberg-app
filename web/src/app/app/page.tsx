// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Nimesh Cheedella

import { redirect } from "next/navigation";

import { auth, signOut } from "@/lib/auth";

export const metadata = { title: "Heisenberg IDE" };

/**
 * Authenticated shell placeholder. Todo 17 lands the real iframe at
 * /ide-bundle/. For now this confirms the auth round-trip works end-to-end:
 * an authenticated user lands here; an unauthenticated one is redirected
 * to /login by middleware.ts.
 */
export default async function AppPage() {
  const session = await auth();
  if (!session?.user) {
    redirect("/login?callbackUrl=/app");
  }
  return (
    <main className="mx-auto flex min-h-screen max-w-5xl flex-col px-6 py-12">
      <header className="flex items-center justify-between">
        <div>
          <div className="font-mono text-sm text-muted-foreground">Heisenberg IDE</div>
          <h1 className="mt-2 text-3xl font-semibold">
            Welcome, {session.user.name ?? session.user.email}
          </h1>
        </div>
        <form
          action={async () => {
            "use server";
            await signOut({ redirectTo: "/" });
          }}
        >
          <button
            type="submit"
            className="rounded-md border border-border px-3 py-1.5 text-sm hover:bg-muted"
          >
            Sign out
          </button>
        </form>
      </header>

      <section className="mt-10 rounded-lg border border-border bg-card p-8">
        <h2 className="text-xl font-semibold">IDE shell — coming up</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          The iframe-mounted Heisenberg IDE lands in todo 17. For now you&apos;re fully signed in;
          visit{" "}
          <a className="text-primary hover:underline" href="/account/security">
            /account/security
          </a>{" "}
          to see the auth round-trip.
        </p>
      </section>
    </main>
  );
}
