"use client";

import * as React from "react";
import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { signIn, useSession } from "next-auth/react";
import { Github, Loader2 } from "lucide-react";

import { Panel } from "@/components/cfo/Panel";
import { ThemeToggle } from "@/components/cfo/ThemeToggle";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { InputOTP, InputOTPGroup, InputOTPSlot } from "@/components/ui/input-otp";
import { Separator } from "@/components/ui/separator";
import { api, isApiError, setToken } from "@/lib/api";

type Step = "password" | "otp";

interface LoginStep1Response {
  status: "otp_required" | "authenticated";
  user_id: string;
  temp_token?: string | null;
  access_token?: string | null;
  tenant_id?: string | null;
}

interface OtpVerifyResponse {
  status: "webauthn_required" | "webauthn_registration_required";
  user_id: string;
  temp_token: string;
}

interface WebAuthnBypassResponse {
  access_token: string;
  token_type: string;
  user_id: string;
  bypass: boolean;
}

function FormError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div
      role="alert"
      aria-live="assertive"
      className="rounded-md border px-3 py-2 text-[12.5px] leading-relaxed"
      style={{ borderColor: "var(--destructive)", color: "var(--destructive)", background: "color-mix(in oklab, var(--destructive) 8%, transparent)" }}
    >
      {message}
    </div>
  );
}

function GoogleIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden>
      <path fill="#4285F4" d="M23.52 12.27c0-.85-.08-1.67-.22-2.45H12v4.64h6.47a5.54 5.54 0 0 1-2.4 3.63v3h3.87c2.27-2.09 3.58-5.17 3.58-8.82Z" />
      <path fill="#34A853" d="M12 24c3.24 0 5.96-1.07 7.94-2.91l-3.87-3c-1.08.72-2.46 1.15-4.07 1.15-3.13 0-5.78-2.11-6.73-4.96H1.27v3.11A11.999 11.999 0 0 0 12 24Z" />
      <path fill="#FBBC05" d="M5.27 14.28A7.2 7.2 0 0 1 4.89 12c0-.79.14-1.56.38-2.28V6.61H1.27A12 12 0 0 0 0 12c0 1.94.46 3.77 1.27 5.39l4-3.11Z" />
      <path fill="#EA4335" d="M12 4.76c1.77 0 3.35.61 4.6 1.8l3.44-3.44C17.95 1.19 15.24 0 12 0 7.31 0 3.26 2.69 1.27 6.61l4 3.11C6.22 6.87 8.87 4.76 12 4.76Z" />
    </svg>
  );
}

interface LoginFormProps {
  /** Read server-side from AUTH_GOOGLE_ID / AUTH_GITHUB_ID (see page.tsx) —
   * NextAuth registers both providers unconditionally in src/auth.ts, so
   * without this the buttons below would navigate straight into NextAuth's
   * raw "Server error / problem with the server configuration" page
   * instead of failing inside our own UI. */
  googleEnabled: boolean;
  githubEnabled: boolean;
}

function LoginPageInner({ googleEnabled, githubEnabled }: LoginFormProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { data: session, status: sessionStatus } = useSession();

  const returnTo = (() => {
    const raw = searchParams?.get("returnTo") || "/dashboard";
    return raw.startsWith("/") && !raw.startsWith("//") ? raw : "/dashboard";
  })();

  // ---- credentials flow ----
  const [step, setStep] = useState<Step>("password");
  const [userId, setUserId] = useState("");
  const [password, setPassword] = useState("");
  const [otp, setOtp] = useState("");
  const [tempToken, setTempToken] = useState("");
  const [loading, setLoading] = useState<"password" | "otp" | "google" | "github" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [resendCooldown, setResendCooldown] = useState(0);

  useEffect(() => {
    if (resendCooldown <= 0) return;
    const t = setTimeout(() => setResendCooldown((s) => s - 1), 1000);
    return () => clearTimeout(t);
  }, [resendCooldown]);

  // ---- SSO return: once NextAuth has a session with a CloudCare token
  // attached (src/auth.ts), finish the handoff and redirect. Deliberately
  // done here (not only in SessionSync) so the redirect only fires once
  // the token is actually stored — see middleware.ts's cookie check,
  // which would otherwise race a redirect straight to a protected route.
  useEffect(() => {
    if (sessionStatus !== "authenticated") return;
    const token = (session as { cloudcareAccessToken?: string } | null)?.cloudcareAccessToken;
    if (!token) return;
    setToken(token);
    router.replace(returnTo);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session, sessionStatus]);

  async function completeLogin(access_token: string) {
    setToken(access_token);
    router.push(returnTo);
  }

  async function handlePasswordSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!userId || !password) {
      setError("Enter your user ID and password.");
      return;
    }
    setLoading("password");
    try {
      const data = await api.post<LoginStep1Response>("/v1/auth/login", { user_id: userId, password });
      if (data.status === "authenticated" && data.access_token) {
        await completeLogin(data.access_token);
        return;
      }
      if (data.temp_token) {
        setTempToken(data.temp_token);
        setStep("otp");
        setResendCooldown(60);
      }
    } catch (err) {
      setError(isApiError(err) ? err.message : "Could not reach the CloudCare API.");
    } finally {
      setLoading(null);
    }
  }

  async function handleOtpSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (otp.length !== 6) {
      setError("Enter the 6-digit code.");
      return;
    }
    setLoading("otp");
    try {
      const verified = await api.post<OtpVerifyResponse>("/v1/auth/otp/verify", { temp_token: tempToken, otp });
      // Third factor (WebAuthn) is intentionally skipped from the UI — see
      // apps/api/routers/auth.py's webauthn/bypass endpoint, left in place
      // unmodified so a real third factor can be switched on later without
      // a rewrite. Called here silently: no WebAuthn prompt is ever shown.
      const bypassed = await api.post<WebAuthnBypassResponse>("/v1/auth/webauthn/bypass", {
        temp_token: verified.temp_token,
      });
      await completeLogin(bypassed.access_token);
    } catch (err) {
      setError(isApiError(err) ? err.message : "Verification failed.");
    } finally {
      setLoading(null);
    }
  }

  async function handleResend() {
    if (resendCooldown > 0) return;
    setError(null);
    try {
      await api.post("/v1/auth/otp/resend", { temp_token: tempToken });
      setResendCooldown(60);
    } catch (err) {
      setError(isApiError(err) ? err.message : "Could not resend the code.");
    }
  }

  async function handleSso(provider: "google" | "github") {
    setError(null);
    setLoading(provider);
    try {
      await signIn(provider, { callbackUrl: `/login?returnTo=${encodeURIComponent(returnTo)}` });
    } finally {
      setLoading(null);
    }
  }

  const ssoConfigured = googleEnabled || githubEnabled;

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-6 py-12">
      <div className="w-full max-w-3xl">
        <div className="stage mb-6 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2.5 font-display text-lg font-bold text-foreground">
            <span className="inline-block h-2 w-2 rounded-full" style={{ background: "var(--signal)" }} />
            CloudCare
          </Link>
          <ThemeToggle />
        </div>

        <div className="grid gap-5 md:grid-cols-2">
          {/* ---- credentials ---- */}
          <Panel eyebrow="Sign in" title="Username & password" subtitle="Password, then a one-time code — two factors.">
            {step === "password" && (
              <form onSubmit={handlePasswordSubmit} className="flex flex-col gap-4" noValidate>
                <div className="grid gap-1.5">
                  <Label htmlFor="userId">User ID</Label>
                  <Input
                    id="userId"
                    value={userId}
                    onChange={(e) => setUserId(e.target.value)}
                    placeholder="demo.user"
                    autoComplete="username"
                    disabled={loading !== null}
                  />
                </div>
                <div className="grid gap-1.5">
                  <Label htmlFor="password">Password</Label>
                  <Input
                    id="password"
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                    autoComplete="current-password"
                    disabled={loading !== null}
                  />
                </div>
                <FormError message={error} />
                <Button type="submit" disabled={loading !== null}>
                  {loading === "password" && <Loader2 className="size-4 animate-spin" />}
                  Continue
                </Button>
                <p className="num text-[11px] text-ink-faint">Demo: demo.user / password123</p>
              </form>
            )}

            {step === "otp" && (
              <form onSubmit={handleOtpSubmit} className="flex flex-col gap-4" noValidate>
                <div className="grid gap-1.5">
                  <Label htmlFor="otp">6-digit verification code</Label>
                  <InputOTP id="otp" maxLength={6} value={otp} onChange={setOtp} disabled={loading !== null}>
                    <InputOTPGroup>
                      <InputOTPSlot index={0} />
                      <InputOTPSlot index={1} />
                      <InputOTPSlot index={2} />
                      <InputOTPSlot index={3} />
                      <InputOTPSlot index={4} />
                      <InputOTPSlot index={5} />
                    </InputOTPGroup>
                  </InputOTP>
                  <p className="text-[11.5px] text-ink-faint">Sent to the email on file. Expires in 5 minutes.</p>
                </div>
                <FormError message={error} />
                <Button type="submit" disabled={loading !== null || otp.length !== 6}>
                  {loading === "otp" && <Loader2 className="size-4 animate-spin" />}
                  Verify
                </Button>
                <div className="flex items-center justify-between">
                  <button
                    type="button"
                    onClick={() => {
                      setStep("password");
                      setOtp("");
                      setError(null);
                    }}
                    className="text-[12px] font-medium text-ink-faint hover:text-foreground"
                  >
                    ← Back
                  </button>
                  <button
                    type="button"
                    onClick={handleResend}
                    disabled={resendCooldown > 0}
                    className="text-[12px] font-semibold text-ink-dim hover:text-foreground disabled:opacity-50"
                  >
                    {resendCooldown > 0 ? `Resend in ${resendCooldown}s` : "Resend code"}
                  </button>
                </div>
              </form>
            )}
          </Panel>

          {/* ---- SSO ---- */}
          <Panel eyebrow="Sign in" title="Single sign-on" subtitle="One click. Google or GitHub." delay={80}>
            <div className="flex flex-col gap-3">
              <Button
                type="button"
                variant="outline"
                onClick={() => handleSso("google")}
                disabled={loading !== null || !googleEnabled}
                title={googleEnabled ? undefined : "Not configured — set AUTH_GOOGLE_ID / AUTH_GOOGLE_SECRET"}
              >
                {loading === "google" ? <Loader2 className="size-4 animate-spin" /> : <GoogleIcon />}
                Continue with Google
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={() => handleSso("github")}
                disabled={loading !== null || !githubEnabled}
                title={githubEnabled ? undefined : "Not configured — set AUTH_GITHUB_ID / AUTH_GITHUB_SECRET"}
              >
                {loading === "github" ? <Loader2 className="size-4 animate-spin" /> : <Github className="size-4" />}
                Continue with GitHub
              </Button>
              <Separator className="my-1" />
              {ssoConfigured ? (
                <p className="text-[11.5px] leading-relaxed text-ink-faint">
                  First sign-in creates your CloudCare account automatically. Returning users are
                  linked by email if they already have a password account.
                </p>
              ) : (
                <p role="status" className="text-[11.5px] leading-relaxed" style={{ color: "var(--ember)" }}>
                  Single sign-on isn&apos;t configured on this deployment yet — set
                  AUTH_GOOGLE_ID/SECRET and AUTH_GITHUB_ID/SECRET in apps/frontend/.env.local
                  (see .env.local.example) to enable it.
                </p>
              )}
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}

export function LoginForm(props: LoginFormProps) {
  return (
    <Suspense fallback={null}>
      <LoginPageInner {...props} />
    </Suspense>
  );
}
