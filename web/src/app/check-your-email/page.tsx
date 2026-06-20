// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Nimesh Cheedella

import Link from "next/link";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export const metadata = { title: "Check your email · Heisenberg" };

export default function CheckYourEmailPage() {
  return (
    <main className="flex min-h-screen items-center justify-center px-6 py-12">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Check your email</CardTitle>
          <CardDescription>
            We sent you a verification link. Click it to activate your account.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4 text-sm text-muted-foreground">
          <p>The link expires in 1 hour.</p>
          <p>
            Didn&apos;t get it? Check your spam folder, then{" "}
            <Link href="/login" className="text-primary hover:underline">
              try signing in
            </Link>{" "}
            and request a new link.
          </p>
        </CardContent>
      </Card>
    </main>
  );
}
