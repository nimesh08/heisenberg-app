// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Nimesh Cheedella

/**
 * Auth.js v5 configuration.
 *
 * Providers (each enabled iff its env vars are present, so dev can run
 * without registering every OAuth app):
 *   - Google (OAuth)
 *   - GitHub (OAuth)
 *   - Microsoft Entra ID (OAuth)
 *   - Email magic link (Nodemailer -> AWS SES SMTP)
 *   - Credentials (email + password; verifies via FastAPI /api/v1/auth/verify-credentials)
 *
 * Adapter: @auth/pg-adapter writing to the SAME Postgres jobsvc uses (tables
 * `users`, `accounts`, `sessions`, `verification_tokens`, `authenticators`).
 *
 * Session strategy: `database` for OAuth/Email (Auth.js DB-backed sessions),
 * `jwt` doesn't work cleanly with @auth/pg-adapter. The session cookie is
 * `__Secure-authjs.session-token` (HttpOnly, SameSite=Lax, Secure in prod).
 *
 * Whenever a user successfully signs in via OAuth/Email, the `signIn` event
 * mirrors the user into the FastAPI `users` row via `upsertFromOAuth`.
 */

import PgAdapter from "@auth/pg-adapter";
import NextAuth from "next-auth";
import type { NextAuthConfig } from "next-auth";
import Credentials from "next-auth/providers/credentials";
import GitHub from "next-auth/providers/github";
import Google from "next-auth/providers/google";
import MicrosoftEntraID from "next-auth/providers/microsoft-entra-id";
import Nodemailer from "next-auth/providers/nodemailer";
import { Pool } from "pg";

import { authBaseConfig } from "./auth.config";
import { env } from "./env";
import { upsertFromOAuth, verifyCredentials } from "./jobsvc";

// One process-wide pg Pool. Hot-reload safety in dev: stash on globalThis.
declare global {
  // eslint-disable-next-line no-var
  var __heisenbergPgPool: Pool | undefined;
}

function getPool(): Pool {
  if (!globalThis.__heisenbergPgPool) {
    globalThis.__heisenbergPgPool = new Pool({
      connectionString: env.DATABASE_URL,
      max: 10,
    });
  }
  return globalThis.__heisenbergPgPool;
}

function buildProviders(): NextAuthConfig["providers"] {
  const providers: NextAuthConfig["providers"] = [];

  if (env.GOOGLE_CLIENT_ID && env.GOOGLE_CLIENT_SECRET) {
    providers.push(
      Google({
        clientId: env.GOOGLE_CLIENT_ID,
        clientSecret: env.GOOGLE_CLIENT_SECRET,
        allowDangerousEmailAccountLinking: true,
      }),
    );
  }
  if (env.GITHUB_CLIENT_ID && env.GITHUB_CLIENT_SECRET) {
    providers.push(
      GitHub({
        clientId: env.GITHUB_CLIENT_ID,
        clientSecret: env.GITHUB_CLIENT_SECRET,
        allowDangerousEmailAccountLinking: true,
      }),
    );
  }
  if (env.MICROSOFT_CLIENT_ID && env.MICROSOFT_CLIENT_SECRET) {
    providers.push(
      MicrosoftEntraID({
        clientId: env.MICROSOFT_CLIENT_ID,
        clientSecret: env.MICROSOFT_CLIENT_SECRET,
        allowDangerousEmailAccountLinking: true,
      }),
    );
  }

  if (env.SES_SMTP_HOST && env.SES_SMTP_USER && env.SES_SMTP_PASS) {
    providers.push(
      Nodemailer({
        server: {
          host: env.SES_SMTP_HOST,
          port: env.SES_SMTP_PORT,
          auth: { user: env.SES_SMTP_USER, pass: env.SES_SMTP_PASS },
          secure: env.SES_SMTP_PORT === 465,
        },
        from: env.EMAIL_FROM,
      }),
    );
  }

  // Credentials provider: email + password; verify via FastAPI.
  providers.push(
    Credentials({
      id: "credentials",
      name: "Email & password",
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" },
      },
      async authorize(creds) {
        const email = String(creds?.email ?? "").trim();
        const password = String(creds?.password ?? "");
        if (!email || !password) return null;
        const verified = await verifyCredentials(email, password);
        if (!verified) return null;
        return {
          id: verified.user_id,
          email,
          emailVerified: verified.email_verified ? new Date() : null,
        };
      },
    }),
  );

  return providers;
}

export const authConfig: NextAuthConfig = {
  ...authBaseConfig,
  adapter: PgAdapter(getPool()),
  providers: buildProviders(),

  // 'database' is required when adapter is set + you want OAuth/email magic-links
  // to issue server-side sessions (the only way to revoke per-session).
  session: { strategy: "database" },

  // Cookies — `__Secure-` prefix is auto-applied in production by Auth.js when
  // `useSecureCookies` is true (the default when NEXTAUTH_URL/AUTH_URL is https://).
  cookies: {
    sessionToken: {
      name:
        env.NODE_ENV === "production" ? "__Secure-authjs.session-token" : "authjs.session-token",
      options: {
        httpOnly: true,
        sameSite: "lax",
        secure: env.NODE_ENV === "production",
        path: "/",
      },
    },
  },

  secret: env.AUTH_SECRET,

  events: {
    /**
     * Mirror the OAuth user into FastAPI on every successful sign-in. Idempotent.
     * Failures are logged but do not block sign-in (the user already authenticated
     * with the upstream provider; jobsvc upsert can be replayed on next login).
     */
    async signIn({ user, account, profile }) {
      if (!account || account.type === "credentials") return;
      if (!user.email) return;
      try {
        await upsertFromOAuth({
          email: user.email,
          name: user.name ?? profile?.name ?? null,
          image: user.image ?? null,
          email_verified: account.provider === "email",
          provider: account.provider,
          provider_account_id: account.providerAccountId,
        });
      } catch (e) {
        console.error("[auth] upsertFromOAuth failed:", e);
      }
    },
  },
};

export const { handlers, auth, signIn, signOut } = NextAuth(authConfig);
