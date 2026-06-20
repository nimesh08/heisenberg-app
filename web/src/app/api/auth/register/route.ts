// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Nimesh Cheedella

import { NextResponse } from "next/server";
import { z } from "zod";

import { JobsvcError, register } from "@/lib/jobsvc";

const schema = z.object({
  email: z.string().email(),
  password: z.string().min(12).max(1024),
  accept_terms: z.literal(true),
});

export async function POST(req: Request) {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ detail: "invalid_json" }, { status: 400 });
  }
  const parsed = schema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      { detail: "validation_error", issues: parsed.error.issues },
      { status: 400 },
    );
  }
  try {
    const result = await register(parsed.data);
    return NextResponse.json(result, { status: 201 });
  } catch (e) {
    if (e instanceof JobsvcError) {
      // Surface the FastAPI detail (e.g. "password_breached") to the form.
      return NextResponse.json(e.detail ?? { detail: "register_failed" }, {
        status: e.status,
      });
    }
    console.error("[register] unexpected error:", e);
    return NextResponse.json({ detail: "internal_error" }, { status: 500 });
  }
}
