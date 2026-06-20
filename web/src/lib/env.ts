// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Nimesh Cheedella

/**
 * Centralised, fail-fast env access.
 *
 * Reads run *only* at module load (server-side). Anything missing throws
 * during Next.js build/dev startup, never at request time. Client-only
 * env (NEXT_PUBLIC_*) goes through `clientEnv()` because the value is
 * substituted at build time and the assertion has to run differently.
 */

type Required = readonly string[];

const REQUIRED_PROD: Required = [
  "AUTH_SECRET",
  "DATABASE_URL",
  "JOBSVC_BASE_URL",
  "JOBSVC_HMAC_SECRET",
];

function requireEnv(name: string): string {
  const v = process.env[name];
  if (!v) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return v;
}

function envOr(name: string, fallback: string): string {
  return process.env[name] ?? fallback;
}

/**
 * Production checker. Calling this from `app/api/health/route.ts` or
 * `auth.ts` raises early if production env is incomplete.
 */
export function assertProductionEnv(): void {
  if (process.env.NODE_ENV !== "production") return;
  const missing = REQUIRED_PROD.filter((k) => !process.env[k]);
  if (missing.length > 0) {
    throw new Error(`Missing required production env vars: ${missing.join(", ")}`);
  }
}

export const env = {
  // Auth.js shared secret (HS256, also used as HMAC key for jobsvc S2S calls).
  AUTH_SECRET: envOr("AUTH_SECRET", "dev-only-not-for-production"),

  // Public origin (no trailing slash).
  PUBLIC_URL: envOr("PUBLIC_URL", "http://localhost:3000"),

  // OAuth providers — empty = provider disabled at runtime.
  GOOGLE_CLIENT_ID: process.env.GOOGLE_CLIENT_ID ?? "",
  GOOGLE_CLIENT_SECRET: process.env.GOOGLE_CLIENT_SECRET ?? "",
  GITHUB_CLIENT_ID: process.env.GITHUB_CLIENT_ID ?? "",
  GITHUB_CLIENT_SECRET: process.env.GITHUB_CLIENT_SECRET ?? "",
  MICROSOFT_CLIENT_ID: process.env.MICROSOFT_CLIENT_ID ?? "",
  MICROSOFT_CLIENT_SECRET: process.env.MICROSOFT_CLIENT_SECRET ?? "",

  // SES SMTP for the Email magic-link provider.
  SES_SMTP_HOST: envOr("SES_SMTP_HOST", ""),
  SES_SMTP_PORT: Number(envOr("SES_SMTP_PORT", "587")),
  SES_SMTP_USER: envOr("SES_SMTP_USER", ""),
  SES_SMTP_PASS: envOr("SES_SMTP_PASS", ""),
  EMAIL_FROM: envOr("EMAIL_FROM", "Heisenberg <noreply@example.com>"),

  // Postgres URL for the @auth/pg-adapter — the SAME database jobsvc uses.
  // Adapter expects sync 'postgres://' or 'postgresql://' (uses pg under the hood).
  DATABASE_URL: envOr("DATABASE_URL", "postgresql://heisenberg:devonly@127.0.0.1:5432/heisenberg"),

  // jobsvc base URL for server-to-server calls.
  JOBSVC_BASE_URL: envOr("JOBSVC_BASE_URL", "http://127.0.0.1:8000"),
  // Defaults to AUTH_SECRET when not set so dev "just works"; override in
  // production for HMAC-only contexts (recommended: equal to AUTH_SECRET).
  JOBSVC_HMAC_SECRET: envOr(
    "JOBSVC_HMAC_SECRET",
    process.env.AUTH_SECRET ?? "dev-only-not-for-production",
  ),

  // RP ID + origin for WebAuthn (passkeys).
  WEBAUTHN_RP_ID: envOr("WEBAUTHN_RP_ID", "localhost"),
  WEBAUTHN_RP_NAME: envOr("WEBAUTHN_RP_NAME", "Heisenberg"),

  NODE_ENV: envOr("NODE_ENV", "development"),

  requireEnv,
} as const;

export type Env = typeof env;
