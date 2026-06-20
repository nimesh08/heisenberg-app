// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Nimesh Cheedella

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export const metadata = { title: "Account security · Heisenberg" };

/**
 * Account security UI scaffold (item #8 in the plan).
 *
 * This page lists the controls a user has to harden their account:
 * - Linked accounts (OAuth providers and Email)
 * - Passkeys (WebAuthn)
 * - TOTP MFA enrolment
 * - Password change
 * - Sign-out-everywhere (revokes the session family)
 *
 * The interactive controls (passkey enrol, TOTP enable, password change)
 * land alongside the matching jobsvc routes in todo 14 (BYOK) and a small
 * follow-up — for v1's first chat we ship the page structure + the visible
 * "you have/don't have" state, gated by the auth session.
 */
export default function AccountSecurityPage() {
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">Security</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Strengthen your account with a passkey or a TOTP code.
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle>Passkeys</CardTitle>
          <CardDescription>
            Sign in with your fingerprint, face, or hardware key. Phishing-resistant.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Passkey enrolment lands with the BYOK + settings workstream. Watch this space.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Two-factor (TOTP)</CardTitle>
          <CardDescription>
            Add a one-time-code generator (Authy, Google Authenticator, 1Password).
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            TOTP enrolment will appear here after the first deploy.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Password</CardTitle>
          <CardDescription>
            Used only when signing in with email + password. We never log it; it&apos;s stored as an
            Argon2id hash.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Change-password form ships next to the BYOK settings.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
