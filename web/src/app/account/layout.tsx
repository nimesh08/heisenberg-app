// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Nimesh Cheedella

import Link from "next/link";
import { redirect } from "next/navigation";
import type { ReactNode } from "react";

import { auth, signOut } from "@/lib/auth";

const NAV: { href: string; label: string }[] = [
  { href: "/account/security", label: "Security" },
  { href: "/account/byok", label: "Provider keys" },
  { href: "/billing", label: "Billing" },
];

export default async function AccountLayout({ children }: { children: ReactNode }) {
  const session = await auth();
  if (!session?.user) {
    redirect("/login?callbackUrl=/account/security");
  }

  return (
    <div className="mx-auto flex w-full max-w-5xl gap-8 px-6 py-10">
      <aside className="w-56 shrink-0">
        <div className="mb-6 text-lg font-semibold">{session.user.email}</div>
        <nav className="flex flex-col gap-1 text-sm">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="rounded-md px-3 py-2 text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              {item.label}
            </Link>
          ))}
          <form
            action={async () => {
              "use server";
              await signOut({ redirectTo: "/" });
            }}
          >
            <button
              type="submit"
              className="mt-2 w-full rounded-md px-3 py-2 text-left text-sm text-red-400 hover:bg-red-950/40"
            >
              Sign out
            </button>
          </form>
        </nav>
      </aside>
      <main className="flex-1">{children}</main>
    </div>
  );
}
