// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Nimesh Cheedella

"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { signIn } from "next-auth/react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const schema = z.object({
  email: z.string().email("Enter a valid email"),
  password: z.string().min(1, "Required"),
});
type FormValues = z.infer<typeof schema>;

export function LoginForm({ callbackUrl }: { callbackUrl: string }) {
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(values: FormValues) {
    setError(null);
    const res = await signIn("credentials", {
      ...values,
      redirect: false,
      callbackUrl,
    });
    if (res?.error) {
      setError("Invalid email or password.");
      return;
    }
    if (res?.url) {
      window.location.assign(res.url);
    }
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="email">Email</Label>
        <Input
          id="email"
          type="email"
          autoComplete="email"
          {...register("email")}
          aria-invalid={errors.email ? "true" : "false"}
        />
        {errors.email ? <p className="text-xs text-red-400">{errors.email.message}</p> : null}
      </div>

      <div className="space-y-2">
        <Label htmlFor="password">Password</Label>
        <Input
          id="password"
          type="password"
          autoComplete="current-password"
          {...register("password")}
          aria-invalid={errors.password ? "true" : "false"}
        />
        {errors.password ? <p className="text-xs text-red-400">{errors.password.message}</p> : null}
      </div>

      {error ? <p className="text-sm text-red-400">{error}</p> : null}

      <Button type="submit" className="w-full" disabled={isSubmitting}>
        {isSubmitting ? "Signing in…" : "Sign in"}
      </Button>
    </form>
  );
}
