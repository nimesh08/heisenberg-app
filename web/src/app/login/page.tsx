// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Nimesh Cheedella

import Link from "next/link";

import { LoginForm } from "@/components/auth/login-form";
import { ProviderButtons } from "@/components/auth/provider-buttons";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { authConfig } from "@/lib/auth";

export const metadata = { title: "Sign in · Heisenberg" };

function enabledProviders(): string[] {
  return (authConfig.providers ?? [])
    .map((p) => (typeof p === "function" ? null : (p as { id?: string }).id))
    .filter((x): x is string => Boolean(x));
}

export default function LoginPage({
  searchParams,
}: {
  searchParams?: { error?: string; callbackUrl?: string };
}) {
  const ids = enabledProviders();
  const callbackUrl = searchParams?.callbackUrl || "/app";

  return (
    <main className="flex min-h-screen items-center justify-center px-6 py-12">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Sign in</CardTitle>
          <CardDescription>Welcome back to Heisenberg. Pick your sign-in method.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {searchParams?.error ? (
            <div className="rounded-md border border-red-700 bg-red-950/40 px-3 py-2 text-sm text-red-300">
              Sign-in failed. Check your credentials and try again.
            </div>
          ) : null}

          <ProviderButtons providers={ids} callbackUrl={callbackUrl} />

          <div className="relative">
            <div className="absolute inset-0 flex items-center">
              <span className="w-full border-t border-border" />
            </div>
            <div className="relative flex justify-center text-xs">
              <span className="bg-card px-2 text-muted-foreground">or continue with email</span>
            </div>
          </div>

          <LoginForm callbackUrl={callbackUrl} />

          <p className="text-center text-sm text-muted-foreground">
            New here?{" "}
            <Link href="/signup" className="text-primary hover:underline">
              Create an account
            </Link>
          </p>
        </CardContent>
      </Card>
    </main>
  );
}
