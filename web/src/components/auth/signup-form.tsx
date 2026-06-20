// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Nimesh Cheedella

"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const schema = z
  .object({
    email: z.string().email("Enter a valid email"),
    password: z.string().min(12, "Use at least 12 characters").max(1024, "Too long"),
    confirm: z.string(),
    accept_terms: z.literal(true, {
      message: "You must accept the terms to continue",
    }),
  })
  .refine((d) => d.password === d.confirm, {
    path: ["confirm"],
    message: "Passwords don't match",
  });
type FormValues = z.infer<typeof schema>;

export function SignupForm() {
  const router = useRouter();
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });
  const [serverError, setServerError] = useState<string | null>(null);

  async function onSubmit(values: FormValues) {
    setServerError(null);
    const res = await fetch("/api/auth/register", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        email: values.email,
        password: values.password,
        accept_terms: values.accept_terms,
      }),
    });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) {
      if (json?.detail === "password_breached") {
        setServerError("This password appears in known breaches. Pick a different one.");
        return;
      }
      setServerError("Something went wrong. Try again.");
      return;
    }
    router.push("/check-your-email");
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="email">Email</Label>
        <Input id="email" type="email" autoComplete="email" {...register("email")} />
        {errors.email ? <p className="text-xs text-red-400">{errors.email.message}</p> : null}
      </div>

      <div className="space-y-2">
        <Label htmlFor="password">Password</Label>
        <Input
          id="password"
          type="password"
          autoComplete="new-password"
          {...register("password")}
        />
        {errors.password ? (
          <p className="text-xs text-red-400">{errors.password.message}</p>
        ) : (
          <p className="text-xs text-muted-foreground">
            12+ characters. We check it against the HIBP breach corpus.
          </p>
        )}
      </div>

      <div className="space-y-2">
        <Label htmlFor="confirm">Confirm password</Label>
        <Input id="confirm" type="password" autoComplete="new-password" {...register("confirm")} />
        {errors.confirm ? <p className="text-xs text-red-400">{errors.confirm.message}</p> : null}
      </div>

      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          className="mt-1"
          {...register("accept_terms")}
          aria-invalid={errors.accept_terms ? "true" : "false"}
        />
        <span>
          I agree to the{" "}
          <Link href="/terms" className="text-primary underline-offset-2 hover:underline">
            Terms
          </Link>{" "}
          and{" "}
          <Link href="/privacy" className="text-primary underline-offset-2 hover:underline">
            Privacy Policy
          </Link>
          .
        </span>
      </label>
      {errors.accept_terms ? (
        <p className="text-xs text-red-400">{errors.accept_terms.message}</p>
      ) : null}

      {serverError ? <p className="text-sm text-red-400">{serverError}</p> : null}

      <Button type="submit" className="w-full" disabled={isSubmitting}>
        {isSubmitting ? "Creating account…" : "Create account"}
      </Button>
    </form>
  );
}
