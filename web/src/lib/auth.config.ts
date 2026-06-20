// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Nimesh Cheedella

/**
 * Edge-safe auth config. Used by `middleware.ts`, which runs on the Edge
 * runtime where Node-only modules (pg, node:crypto, nodemailer) aren't
 * available. The middleware only needs the `authorized` callback to gate
 * routes — it never instantiates providers or hits the DB.
 *
 * The full config (adapter, providers, events) lives in `auth.ts` and is
 * used by the route handlers which run on the Node runtime.
 */

import type { NextAuthConfig } from "next-auth";

export const authBaseConfig: NextAuthConfig = {
  providers: [],
  pages: {
    signIn: "/login",
    error: "/login",
    verifyRequest: "/check-your-email",
    newUser: "/welcome",
  },
  callbacks: {
    authorized({ auth, request }) {
      const { pathname } = request.nextUrl;
      const isPublic =
        pathname === "/" ||
        pathname.startsWith("/login") ||
        pathname.startsWith("/signup") ||
        pathname.startsWith("/check-your-email") ||
        pathname.startsWith("/api/auth") ||
        pathname.startsWith("/api/health") ||
        pathname.startsWith("/_next") ||
        pathname === "/privacy" ||
        pathname === "/terms" ||
        pathname === "/favicon.ico";
      if (isPublic) return true;
      return Boolean(auth?.user);
    },
  },
  trustHost: true,
};
