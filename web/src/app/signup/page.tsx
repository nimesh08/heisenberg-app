// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Nimesh Cheedella

import Link from "next/link";

import { ProviderButtons } from "@/components/auth/provider-buttons";
import { SignupForm } from "@/components/auth/signup-form";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { authConfig } from "@/lib/auth";

export const metadata = { title: "Sign up · Heisenberg" };

function enabledProviders(): string[] {
  return (authConfig.providers ?? [])
    .map((p) => (typeof p === "function" ? null : (p as { id?: string }).id))
    .filter((x): x is string => Boolean(x));
}

export default function SignupPage() {
  const ids = enabledProviders();

  return (
    <main className="flex min-h-screen items-center justify-center px-6 py-12">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Create your account</CardTitle>
          <CardDescription>
            Heisenberg is free to use with your own quantum cloud account.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <ProviderButtons providers={ids} callbackUrl="/app" />

          <div className="relative">
            <div className="absolute inset-0 flex items-center">
              <span className="w-full border-t border-border" />
            </div>
            <div className="relative flex justify-center text-xs">
              <span className="bg-card px-2 text-muted-foreground">or sign up with email</span>
            </div>
          </div>

          <SignupForm />

          <p className="text-center text-sm text-muted-foreground">
            Already have an account?{" "}
            <Link href="/login" className="text-primary hover:underline">
              Sign in
            </Link>
          </p>
        </CardContent>
      </Card>
    </main>
  );
}
