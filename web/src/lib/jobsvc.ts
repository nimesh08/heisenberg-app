// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Nimesh Cheedella

/**
 * Server-to-server client for the FastAPI jobsvc.
 *
 * Every call carries an HMAC-SHA256 of the raw request body in
 * `X-Auth-Hmac`. The HMAC key is JOBSVC_HMAC_SECRET (same value as
 * AUTH_SECRET in v1; can be split later). FastAPI verifies; this is
 * how we authenticate the Auth.js process to jobsvc without sharing
 * cookies across origins.
 *
 * Used by: `auth.ts` (Credentials provider verify, OAuth upsert), the
 * settings/security pages, and the billing routes.
 */

import { createHmac } from "node:crypto";

import { env } from "./env";

export class JobsvcError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: unknown,
  ) {
    super(`jobsvc returned ${status}`);
    this.name = "JobsvcError";
  }
}

function hmacOf(body: string): string {
  return createHmac("sha256", env.JOBSVC_HMAC_SECRET).update(body).digest("hex");
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const raw = JSON.stringify(body);
  const res = await fetch(`${env.JOBSVC_BASE_URL}${path}`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-auth-hmac": hmacOf(raw),
    },
    body: raw,
    cache: "no-store",
  });
  let parsed: unknown = null;
  try {
    parsed = await res.json();
  } catch {
    // Body wasn't JSON — keep null and let the status drive the decision.
  }
  if (!res.ok) {
    throw new JobsvcError(res.status, parsed);
  }
  return parsed as T;
}

// ----- typed surface ---------------------------------------------------------

export interface VerifyCredentialsResponse {
  user_id: string;
  email_verified: boolean;
}

export async function verifyCredentials(
  email: string,
  password: string,
): Promise<VerifyCredentialsResponse | null> {
  try {
    return await postJson<VerifyCredentialsResponse>("/api/v1/auth/verify-credentials", {
      email,
      password,
    });
  } catch (e) {
    if (e instanceof JobsvcError && e.status === 401) {
      return null;
    }
    throw e;
  }
}

export interface UpsertFromOAuthResponse {
  user_id: string;
  created: boolean;
}

export async function upsertFromOAuth(input: {
  email: string;
  name?: string | null;
  image?: string | null;
  email_verified: boolean;
  provider: string;
  provider_account_id: string;
}): Promise<UpsertFromOAuthResponse> {
  return postJson<UpsertFromOAuthResponse>("/api/v1/auth/upsert-from-oauth", input);
}

export interface RegisterResponse {
  user_id: string;
  email_verification_required: boolean;
}

export async function register(input: {
  email: string;
  password: string;
  accept_terms: boolean;
}): Promise<RegisterResponse> {
  return postJson<RegisterResponse>("/api/v1/auth/register", input);
}
