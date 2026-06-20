// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Nimesh Cheedella

/**
 * Edge middleware: uses the slim auth config (no DB/SMTP/jobsvc imports) so
 * Next.js can ship it to the Edge runtime. The full provider/adapter wiring
 * lives in `lib/auth.ts` and runs on the Node runtime in /api/auth/[...].
 */

import NextAuth from "next-auth";

import { authBaseConfig } from "@/lib/auth.config";

export const { auth: middleware } = NextAuth(authBaseConfig);

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\..*).*)"],
};
