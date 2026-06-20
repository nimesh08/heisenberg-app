// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Nimesh Cheedella

"use client";

import { signIn } from "next-auth/react";

import { Button } from "@/components/ui/button";

const PROVIDER_LABELS: Record<string, string> = {
  google: "Continue with Google",
  github: "Continue with GitHub",
  "microsoft-entra-id": "Continue with Microsoft",
  nodemailer: "Email me a magic link",
};

export function ProviderButtons({
  providers,
  callbackUrl,
}: {
  providers: string[];
  callbackUrl: string;
}) {
  // Filter to OAuth + email providers only; the credentials provider is the form below.
  const oauth = providers.filter((id) => id !== "credentials");
  if (oauth.length === 0) return null;

  return (
    <div className="space-y-2">
      {oauth.map((id) => (
        <Button
          key={id}
          variant="outline"
          className="w-full"
          onClick={() => signIn(id, { callbackUrl })}
        >
          {PROVIDER_LABELS[id] ?? `Continue with ${id}`}
        </Button>
      ))}
    </div>
  );
}
