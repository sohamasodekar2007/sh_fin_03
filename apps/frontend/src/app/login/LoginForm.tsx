"use client";

import * as React from "react";
import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { signIn, useSession } from "next-auth/react";
import { startAuthentication, startRegistration } from "@simplewebauthn/browser";
import { Fingerprint, Github, KeyRound, Loader2, ShieldCheck } from "lucide-react";

import { Panel } from "@/components/cfo/Panel";
import { ThemeToggle } from "@/components/cfo/ThemeToggle";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { InputOTP, InputOTPGroup, InputOTPSlot } from "@/components/ui/input-otp";
import { Separator } from "@/components/ui/separator";
import { api, isApiError, setToken } from "@/lib/api";

type Step = "password" | "otp" | "webauthn" | "sso-mfa";
type WebAuthnStatus = "webauthn_required" | "webauthn_registration_required";
type WebAuthnMode = "ready" | "register" | "authenticate" | "unsupported" | "error";

interface LoginStep1Response {
  status: "otp_required" | "authenticated";
  user_id: string;
  temp_token?: string | null;
  access_token?: string | null;
  tenant_id?: string | null;
}

interface OtpVerifyResponse {
  status: WebAuthnStatus;
  user_id: string;
  temp_token: string;
}

interface WebAuthnFinishResponse {
  access_token: string;
  token_type: string;
  user_id: string;
}

interface LoginBypassResponse {
  access_token: string;
  token_type: string;
  user_id: string;
  tenant_id: string;
}

type SsoRegisterOptions = Parameters<typeof startRegistration>[0] & {
  session_id: string;
};

function FormError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div
      role="alert"
      aria-live="assertive"
      className="rounded-md border px-3 py-2 text-[12.5px] leading-relaxed"
      style={{
        borderColor: "var(--destructive)",
        color: "var(--destructive)",
        background: "color-mix(in oklab, var(--destructive) 8%, transparent)",
      }}
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

  const [step, setStep] = useState<Step>("password");
  const [userId, setUserId] = useState("");
  const [password, setPassword] = useState("");
  const [otp, setOtp] = useState("");
  const [tempToken, setTempToken] = useState("");
  const [webauthnStatus, setWebauthnStatus] = useState<WebAuthnStatus>("webauthn_registration_required");
  const [webauthnMode, setWebauthnMode] = useState<WebAuthnMode>("ready");
  const [loading, setLoading] = useState<"password" | "otp" | "webauthn" | "sso-continue" | "sso-2fa" | "sso-3fa" | "bypass" | "google" | "github" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [resendCooldown, setResendCooldown] = useState(0);
  const [otpTimeLeft, setOtpTimeLeft] = useState(0);
  const [ssoAccessToken, setSsoAccessToken] = useState("");

  useEffect(() => {
    if (resendCooldown <= 0) return;
    const t = setTimeout(() => setResendCooldown((s) => s - 1), 1000);
    return () => clearTimeout(t);
  }, [resendCooldown]);

  useEffect(() => {
    if (otpTimeLeft <= 0) return;
    const t = setTimeout(() => setOtpTimeLeft((s) => s - 1), 1000);
    return () => clearTimeout(t);
  }, [otpTimeLeft]);

  useEffect(() => {
    if (sessionStatus !== "authenticated") return;
    const token = (session as { cloudcareAccessToken?: string } | null)?.cloudcareAccessToken;
    if (!token) return;
    setToken(token);
    setSsoAccessToken(token);
    setStep("sso-mfa");
  }, [session, sessionStatus]);

  async function completeLogin(accessToken: string) {
    setToken(accessToken);
    router.push(returnTo);
  }

  function resetToPassword() {
    setStep("password");
    setOtp("");
    setTempToken("");
    setWebauthnMode("ready");
    setError(null);
    setOtpTimeLeft(0);
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
        setOtpTimeLeft(300);
      }
    } catch (err) {
      setError(isApiError(err) ? err.message : "Could not reach the CloudCare API.");
    } finally {
      setLoading(null);
    }
  }

  async function handleBypassLogin() {
    setError(null);
    if (!userId || !password) {
      setError("Enter your user ID and password before using bypass.");
      return;
    }

    setLoading("bypass");
    try {
      const data = await api.post<LoginBypassResponse>("/v1/auth/login/bypass", {
        user_id: userId,
        password,
      });
      await completeLogin(data.access_token);
    } catch (err) {
      setError(isApiError(err) ? err.message : "Bypass login failed.");
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
      setTempToken(verified.temp_token);
      setWebauthnStatus(verified.status);
      setWebauthnMode("ready");
      setStep("webauthn");
      void runWebAuthn(verified.temp_token, verified.status);
    } catch (err) {
      setError(isApiError(err) ? err.message : "Verification failed.");
    } finally {
      setLoading(null);
    }
  }

  async function runWebAuthn(token = tempToken, status = webauthnStatus) {
    setError(null);
    if (!window.PublicKeyCredential) {
      setWebauthnMode("unsupported");
      return;
    }

    setLoading("webauthn");
    try {
      if (status === "webauthn_registration_required") {
        setWebauthnMode("register");
        const options = await api.post<Parameters<typeof startRegistration>[0]>("/v1/auth/webauthn/register/begin", {
          temp_token: token,
        });
        const credential = await startRegistration(options);
        const result = await api.post<WebAuthnFinishResponse>("/v1/auth/webauthn/register/finish", {
          temp_token: token,
          registration_response: credential,
        });
        await completeLogin(result.access_token);
        return;
      }

      setWebauthnMode("authenticate");
      const options = await api.post<Parameters<typeof startAuthentication>[0]>("/v1/auth/webauthn/authenticate/begin", {
        temp_token: token,
      });
      const credential = await startAuthentication(options);
      const result = await api.post<WebAuthnFinishResponse>("/v1/auth/webauthn/authenticate/finish", {
        temp_token: token,
        authentication_response: credential,
      });
      await completeLogin(result.access_token);
    } catch (err) {
      setWebauthnMode("error");
      setError(isApiError(err) ? err.message : err instanceof Error ? err.message : "Passkey verification failed.");
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
      setOtpTimeLeft(300);
      setOtp("");
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

  async function continueSsoWithoutMfa() {
    if (!ssoAccessToken) return;
    setLoading("sso-continue");
    try {
      await api.post("/v1/auth/sso/mfa-preference", { mfa_level: "none" });
      await completeLogin(ssoAccessToken);
    } catch (err) {
      setError(isApiError(err) ? err.message : "Could not save your SSO preference.");
    } finally {
      setLoading(null);
    }
  }

  async function enableSso2fa() {
    if (!ssoAccessToken) return;
    setLoading("sso-2fa");
    try {
      await api.post("/v1/auth/sso/mfa-preference", { mfa_level: "2fa" });
      await completeLogin(ssoAccessToken);
    } catch (err) {
      setError(isApiError(err) ? err.message : "Could not enable SSO 2FA.");
    } finally {
      setLoading(null);
    }
  }

  async function enableSso3fa() {
    if (!ssoAccessToken) return;
    setError(null);
    if (!window.PublicKeyCredential) {
      setError("This browser does not support passkeys.");
      return;
    }

    setLoading("sso-3fa");
    try {
      const options = await api.post<SsoRegisterOptions>("/v1/auth/webauthn/session/register/begin");
      const { session_id: sessionId, ...registrationOptions } = options;
      const credential = await startRegistration(registrationOptions);
      await api.post("/v1/auth/webauthn/session/register/finish", {
        session_id: sessionId,
        registration_response: credential,
      });
      await completeLogin(ssoAccessToken);
    } catch (err) {
      setError(isApiError(err) ? err.message : err instanceof Error ? err.message : "Could not enable SSO 3FA.");
    } finally {
      setLoading(null);
    }
  }

  const ssoConfigured = googleEnabled || githubEnabled;
  const otpClock = `${Math.floor(otpTimeLeft / 60)
    .toString()
    .padStart(2, "0")}:${(otpTimeLeft % 60).toString().padStart(2, "0")}`;

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
          <Panel
            eyebrow="Secure sign in"
            title={step === "sso-mfa" ? "Add extra protection?" : "Password, code, passkey"}
            subtitle={
              step === "sso-mfa"
                ? "Choose how strongly to protect future Google or GitHub sign-ins."
                : "Three factors: something you know, receive, and physically unlock."
            }
          >
            {step === "sso-mfa" && (
              <div className="flex flex-col gap-4">
                <div className="rounded-md border border-border bg-muted/35 p-4">
                  <div className="grid gap-3 text-[12px] text-ink-faint">
                    <div className="flex items-start gap-2">
                      <ShieldCheck className="mt-0.5 size-4 text-primary" />
                      <span>2FA saves your SSO account as requiring an additional verification policy.</span>
                    </div>
                    <div className="flex items-start gap-2">
                      <Fingerprint className="mt-0.5 size-4 text-primary" />
                      <span>3FA enrolls a real device passkey before your dashboard session continues.</span>
                    </div>
                  </div>
                </div>
                <FormError message={error} />
                <div className="grid gap-2">
                  <Button type="button" onClick={enableSso3fa} disabled={loading !== null}>
                    {loading === "sso-3fa" ? <Loader2 className="size-4 animate-spin" /> : <Fingerprint className="size-4" />}
                    Add 3FA passkey
                  </Button>
                  <Button type="button" variant="outline" onClick={enableSso2fa} disabled={loading !== null}>
                    {loading === "sso-2fa" ? <Loader2 className="size-4 animate-spin" /> : <ShieldCheck className="size-4" />}
                    Add 2FA policy
                  </Button>
                  <Button type="button" variant="ghost" onClick={continueSsoWithoutMfa} disabled={loading !== null}>
                    {loading === "sso-continue" && <Loader2 className="size-4 animate-spin" />}
                    Continue without extra factor
                  </Button>
                </div>
              </div>
            )}

            {step === "password" && (
              <form onSubmit={handlePasswordSubmit} className="flex flex-col gap-4" noValidate>
                <div className="grid grid-cols-3 gap-2 rounded-md border border-border bg-muted/35 p-2 text-[11px] font-medium text-ink-faint">
                  <div className="flex items-center gap-1.5 text-foreground">
                    <KeyRound className="size-3.5" />
                    Password
                  </div>
                  <div className="flex items-center gap-1.5">
                    <ShieldCheck className="size-3.5" />
                    OTP
                  </div>
                  <div className="flex items-center gap-1.5">
                    <Fingerprint className="size-3.5" />
                    Passkey
                  </div>
                </div>

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
                    placeholder="password"
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
                  <p className="text-[11.5px] text-ink-faint">
                    Sent to the email on file. Expires in <span className="num">{otpClock}</span>.
                  </p>
                </div>
                <FormError message={error} />
                <Button type="submit" disabled={loading !== null || otp.length !== 6 || otpTimeLeft === 0}>
                  {loading === "otp" && <Loader2 className="size-4 animate-spin" />}
                  Verify code
                </Button>
                <div className="flex items-center justify-between">
                  <button
                    type="button"
                    onClick={resetToPassword}
                    className="text-[12px] font-medium text-ink-faint hover:text-foreground"
                  >
                    Back
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

            {step === "webauthn" && (
              <div className="flex flex-col gap-4">
                <div className="rounded-md border border-border bg-muted/35 p-4 text-center">
                  <div className="mx-auto mb-3 flex size-12 items-center justify-center rounded-md bg-primary/10 text-primary">
                    {loading === "webauthn" ? <Loader2 className="size-5 animate-spin" /> : <Fingerprint className="size-5" />}
                  </div>
                  <p className="text-sm font-semibold text-foreground">
                    {webauthnMode === "register"
                      ? "Create your device passkey"
                      : webauthnMode === "authenticate"
                        ? "Unlock with your passkey"
                        : webauthnMode === "unsupported"
                          ? "Passkeys are not available"
                          : "Passkey required"}
                  </p>
                  <p className="mt-1 text-[11.5px] leading-relaxed text-ink-faint">
                    {webauthnStatus === "webauthn_registration_required"
                      ? "This device will be enrolled before your session is issued."
                      : "Use Windows Hello, Touch ID, Face ID, a PIN, or a security key to finish sign-in."}
                  </p>
                </div>
                <FormError message={error} />
                <Button type="button" onClick={() => runWebAuthn()} disabled={loading !== null || webauthnMode === "unsupported"}>
                  {loading === "webauthn" && <Loader2 className="size-4 animate-spin" />}
                  {webauthnStatus === "webauthn_registration_required" ? "Enroll passkey" : "Verify passkey"}
                </Button>
                <button
                  type="button"
                  onClick={resetToPassword}
                  disabled={loading !== null}
                  className="text-[12px] font-medium text-ink-faint hover:text-foreground disabled:opacity-50"
                >
                  Start over
                </button>
              </div>
            )}
          </Panel>

          <Panel eyebrow="Sign in" title="Single sign-on" subtitle="One click. Google or GitHub." delay={80}>
            <div className="flex flex-col gap-3">
              <Button
                type="button"
                variant="outline"
                onClick={() => handleSso("google")}
                disabled={loading !== null || !googleEnabled}
                title={googleEnabled ? undefined : "Not configured. Set AUTH_GOOGLE_ID / AUTH_GOOGLE_SECRET."}
              >
                {loading === "google" ? <Loader2 className="size-4 animate-spin" /> : <GoogleIcon />}
                Continue with Google
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={() => handleSso("github")}
                disabled={loading !== null || !githubEnabled}
                title={githubEnabled ? undefined : "Not configured. Set AUTH_GITHUB_ID / AUTH_GITHUB_SECRET."}
              >
                {loading === "github" ? <Loader2 className="size-4 animate-spin" /> : <Github className="size-4" />}
                Continue with GitHub
              </Button>
              <Separator className="my-1" />
              {ssoConfigured ? (
                <p className="text-[11.5px] leading-relaxed text-ink-faint">
                  First sign-in creates your CloudCare account automatically. Returning users are linked by email if
                  they already have a password account.
                </p>
              ) : (
                <p role="status" className="text-[11.5px] leading-relaxed" style={{ color: "var(--ember)" }}>
                  Single sign-on is not configured on this deployment yet. Set AUTH_GOOGLE_ID/SECRET and
                  AUTH_GITHUB_ID/SECRET in apps/frontend/.env.local to enable it.
                </p>
              )}
            </div>
          </Panel>
        </div>
      </div>
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={handleBypassLogin}
        disabled={loading !== null}
        className="fixed bottom-4 right-4 z-20 border-amber-500/50 bg-background/95 text-amber-700 shadow-sm backdrop-blur hover:bg-amber-500/10 dark:text-amber-300"
        title="Development/demo only. Verifies password, then skips OTP and passkey."
      >
        {loading === "bypass" ? <Loader2 className="size-4 animate-spin" /> : <ShieldCheck className="size-4" />}
        Bypass 2FA/3FA
      </Button>
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
