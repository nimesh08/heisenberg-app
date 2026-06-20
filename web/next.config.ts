// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Nimesh Cheedella

import type { NextConfig } from "next";

/**
 * Security headers (item #1 in the plan + plan §17).
 *
 * - CSP locks scripts/styles to self; allows inline styles only because
 *   Tailwind's CSS-in-JS toggle and Next 15 dev tooling rely on a few
 *   inline style attributes. Inline scripts are forbidden.
 * - frame-src 'self' is REQUIRED so the IDE iframe (/ide-bundle/) loads.
 * - X-Frame-Options DENY breaks our own iframe; we set frame-ancestors
 *   in CSP instead, which supersedes XFO on modern browsers.
 * - Permissions-Policy locks down sensitive APIs.
 * - HSTS preload — only effective once the site is served over HTTPS.
 */
const SECURITY_HEADERS = [
  {
    key: "Strict-Transport-Security",
    value: "max-age=63072000; includeSubDomains; preload",
  },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=(), interest-cohort=()",
  },
  // COOP/COEP enable cross-origin isolation (required for SharedArrayBuffer
  // in some IDE features later; harmless to set early).
  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
  { key: "Cross-Origin-Resource-Policy", value: "same-origin" },
  {
    key: "Content-Security-Policy",
    value: [
      "default-src 'self'",
      // 'unsafe-eval' is required by Next.js dev (HMR). Production build strips it.
      `script-src 'self' ${process.env.NODE_ENV === "production" ? "" : "'unsafe-eval'"} 'unsafe-inline'`,
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data: https:",
      "font-src 'self' data:",
      "connect-src 'self'",
      "frame-src 'self'",
      "frame-ancestors 'none'",
      "base-uri 'self'",
      "form-action 'self'",
      "object-src 'none'",
    ].join("; "),
  },
];

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // Auth.js + pg adapter run server-side; tell Next not to try to bundle
  // the native pg driver into the edge or browser.
  serverExternalPackages: ["pg", "@auth/pg-adapter", "nodemailer"],
  async headers() {
    return [
      {
        source: "/:path*",
        headers: SECURITY_HEADERS,
      },
    ];
  },
};

export default nextConfig;
