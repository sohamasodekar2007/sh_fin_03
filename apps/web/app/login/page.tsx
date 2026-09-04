"use client";

import { Suspense, useState, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { startRegistration, startAuthentication } from "@simplewebauthn/browser";
import { saveSession } from "@/lib/auth";

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

type Step = "password" | "otp" | "webauthn";
type WebAuthnMode = "checking" | "register" | "authenticate" | "unsupported" | "error";
type FormMode = "login" | "register";

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginPageInner />
    </Suspense>
  );
}

function LoginPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  // Where to send the user after a successful login — set when an
  // unauthenticated click on a Supervisor approval-email link redirects
  // here (see apps/web/app/approve/[token]/page.tsx). Only ever a path on
  // this same site, never an absolute URL, so this can't be used to
  // redirect a logged-in user off-site.
  const returnTo = (() => {
    const raw = searchParams?.get("returnTo") || "/dashboard";
    return raw.startsWith("/") && !raw.startsWith("//") ? raw : "/dashboard";
  })();

  // Input fields
  const [userId, setUserId] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [otp, setOtp] = useState("");

  // Cloud Auth fields
  const [cloudAuthMode, setCloudAuthMode] = useState<"none" | "aws" | "gcp" | "azure">("none");
  const [awsRoleArn, setAwsRoleArn] = useState("");
  const [gcpJson, setGcpJson] = useState("");
  const [azureTenantId, setAzureTenantId] = useState("");
  const [azureClientId, setAzureClientId] = useState("");
  
  // Wizard steps & mode
  const [step, setStep] = useState<Step>("password");
  const [formMode, setFormMode] = useState<FormMode>("login");
  const [tempToken, setTempToken] = useState("");
  const [nextWebauthnStatus, setNextWebauthnStatus] = useState<"webauthn_required" | "webauthn_registration_required">("webauthn_registration_required");
  
  // States
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [successMessage, setSuccessMessage] = useState("");
  const [timer, setTimer] = useState(300); // 5 minutes
  const [resendCooldown, setResendCooldown] = useState(60); // 60 seconds
  const [webauthnMode, setWebauthnMode] = useState<WebAuthnMode>("checking");

  // Timers for OTP
  useEffect(() => {
    if (step === "otp" && timer > 0) {
      const t = setTimeout(() => setTimer(timer - 1), 1000);
      return () => clearTimeout(t);
    }
  }, [step, timer]);

  useEffect(() => {
    if (step === "otp" && resendCooldown > 0) {
      const t = setTimeout(() => setResendCooldown(resendCooldown - 1), 1000);
      return () => clearTimeout(t);
    }
  }, [step, resendCooldown]);

  const formatTime = (secs: number) => {
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
  };

  // Submit Password (Step 1) or Register Account
  const handlePasswordOrRegisterSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setSuccessMessage("");

    if (formMode === "register") {
      if (!userId || !email || !password) {
        setError("Please fill in all fields.");
        return;
      }
      setLoading(true);
      try {
        const res = await fetch(`${BASE_URL}/v1/auth/register`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ user_id: userId, email, password }),
        });
        const data = await res.json();
        if (!res.ok) {
          throw new Error(data.detail || "Account registration failed.");
        }
        setSuccessMessage("Account created successfully! Please log in below.");
        setFormMode("login");
        setPassword(""); // Clear password for security
      } catch (err: any) {
        setError(err.message || "Connection error to registration server.");
      } finally {
        setLoading(false);
      }
    } else {
      if (!userId || !password) {
        setError("Please enter your user ID and password.");
        return;
      }
      setLoading(true);
      try {
        const res = await fetch(`${BASE_URL}/v1/auth/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ user_id: userId, password }),
        });
        const data = await res.json();
        if (!res.ok) {
          throw new Error(data.detail || "Invalid User ID or Password");
        }
        if (data.status === "authenticated" && data.access_token) {
          saveSession(data.user_id || userId, data.access_token);
          router.push(returnTo);
          return;
        }
        setTempToken(data.temp_token);
        setStep("otp");
        setTimer(300);
        setResendCooldown(60);
      } catch (err: any) {
        setError(err.message || "Connection error to authentication server.");
      } finally {
        setLoading(false);
      }
    }
  };

  // Step 2: Verify OTP
  const handleCloudLoginSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    let payload: any = { provider: cloudAuthMode, tenant_id: "demo-tenant" };
    if (cloudAuthMode === "aws") {
      if (!awsRoleArn) { setError("Please enter Role ARN"); setLoading(false); return; }
      payload.role_arn = awsRoleArn;
      payload.account_id = "aws-account"; // placeholder
    } else if (cloudAuthMode === "gcp") {
      if (!gcpJson) { setError("Please paste Service Account JSON"); setLoading(false); return; }
      try { payload.gcp_service_account_json = JSON.parse(gcpJson); payload.account_id = payload.gcp_service_account_json.project_id || "gcp-project"; } 
      catch { setError("Invalid JSON format"); setLoading(false); return; }
    } else if (cloudAuthMode === "azure") {
      if (!azureTenantId || !azureClientId) { setError("Please enter Tenant ID and Client ID"); setLoading(false); return; }
      payload.azure_tenant_id = azureTenantId;
      payload.azure_client_id = azureClientId;
      payload.account_id = "azure-subscription"; // placeholder
    }

    try {
      const res = await fetch(`${BASE_URL}/v1/cloud-accounts/validate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok || !data.validated) {
        throw new Error(data.error || "Cloud authentication failed.");
      }
      
      // On success, we simulate a login by logging them in with a mock cloud session
      saveSession(`${cloudAuthMode}-user`, "mock-cloud-token");
      router.push(returnTo);
    } catch (err: any) {
      setError(err.message || "Failed to authenticate with cloud provider.");
    } finally {
      setLoading(false);
    }
  };

  // Step 2: Verify OTP
  const handleOtpSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!otp) {
      setError("Please enter the verification code.");
      return;
    }
    setError("");
    setLoading(true);
    try {
      const res = await fetch(`${BASE_URL}/v1/auth/otp/verify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ temp_token: tempToken, otp }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Incorrect verification code.");
      }
      setTempToken(data.temp_token);
      setNextWebauthnStatus(data.status);
      setStep("webauthn");
      
      // Auto-trigger WebAuthn
      triggerWebAuthn(data.temp_token, data.status);
    } catch (err: any) {
      setError(err.message || "OTP verification failed.");
    } finally {
      setLoading(false);
    }
  };

  // Resend OTP
  const handleResendOtp = async () => {
    if (resendCooldown > 0) return;
    setError("");
    setLoading(true);
    try {
      const res = await fetch(`${BASE_URL}/v1/auth/otp/resend`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ temp_token: tempToken }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Failed to resend code.");
      }
      setTimer(300);
      setResendCooldown(60);
      setOtp("");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Step 3: WebAuthn Trigger
  const triggerWebAuthn = async (token: string, statusType: "webauthn_required" | "webauthn_registration_required") => {
    setError("");
    setLoading(true);
    
    const isWebAuthnSupported = typeof window !== "undefined" && 
      !!window.PublicKeyCredential;
      
    if (!isWebAuthnSupported) {
      setWebauthnMode("unsupported");
      setLoading(false);
      return;
    }
    
    try {
      if (statusType === "webauthn_registration_required") {
        setWebauthnMode("register");
        // 1. Begin registration
        const optionsRes = await fetch(`${BASE_URL}/v1/auth/webauthn/register/begin`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ temp_token: token }),
        });
        const options = await optionsRes.json();
        if (!optionsRes.ok) throw new Error(options.detail || "Failed to fetch registration options");
        
        // 2. Browser ceremony
        const credential = await startRegistration(options);
        
        // 3. Finish registration
        const finishRes = await fetch(`${BASE_URL}/v1/auth/webauthn/register/finish`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ temp_token: token, registration_response: credential }),
        });
        const result = await finishRes.json();
        if (!finishRes.ok) throw new Error(result.detail || "WebAuthn enrollment rejected");
        
        // Success
        saveSession(result.user_id, result.access_token);
        router.push(returnTo);
      } else {
        setWebauthnMode("authenticate");
        // 1. Begin authentication
        const optionsRes = await fetch(`${BASE_URL}/v1/auth/webauthn/authenticate/begin`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ temp_token: token }),
        });
        const options = await optionsRes.json();
        if (!optionsRes.ok) throw new Error(options.detail || "Failed to fetch verification parameters");
        
        // 2. Browser ceremony
        const credential = await startAuthentication(options);
        
        // 3. Finish authentication
        const finishRes = await fetch(`${BASE_URL}/v1/auth/webauthn/authenticate/finish`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ temp_token: token, authentication_response: credential }),
        });
        const result = await finishRes.json();
        if (!finishRes.ok) throw new Error(result.detail || "WebAuthn verification rejected");
        
        // Success
        saveSession(result.user_id, result.access_token);
        router.push(returnTo);
      }
    } catch (err: any) {
      console.warn("WebAuthn Error:", err);
      setError(err.message || "Biometric validation canceled or key not recognized.");
      setWebauthnMode("error");
    } finally {
      setLoading(false);
    }
  };

  // Bypass WebAuthn (Demo-only fallback)
  const handleBypassWebAuthn = async () => {
    setError("");
    setLoading(true);
    try {
      if (tempToken) {
        const res = await fetch(`${BASE_URL}/v1/auth/webauthn/bypass`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({ temp_token: tempToken }),
        });
        const data = await res.json();
        if (res.ok && data.user_id) {
          saveSession(data.user_id, data.access_token);
        } else {
          saveSession(userId || "demo.user");
        }
      } else {
        saveSession(userId || "demo.user");
      }
      window.location.href = returnTo;
    } catch (err: any) {
      console.warn("Bypass error, using local session:", err);
      saveSession(userId || "demo.user");
      window.location.href = returnTo;
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="min-h-screen flex items-center justify-center bg-bg px-6">
      <div className="w-full max-w-sm">
        <Link href="/" className="flex items-center justify-center gap-2.5 font-display font-bold text-xl text-ink mb-8">
          <span className="w-8 h-8 rounded-[10px] bg-gradient-to-br from-brandBlue to-brandTeal inline-block" />
          CloudCare
        </Link>

        <div className="bg-surface border border-line rounded-lg2 shadow-soft p-8 transition-all duration-300">
          
          {/* STEP 1: PASSWORD OR REGISTER */}
          {step === "password" && (
            <>
              <h1 className="font-display text-xl font-semibold text-ink mb-1">
                {formMode === "login" ? "Welcome back" : "Create an Account"}
              </h1>
              <p className="text-sm text-inkSoft mb-6">
                {formMode === "login" ? "Log in to view your cloud cost dashboard." : "Sign up below to protect your dashboard."}
              </p>
              
              {successMessage && <div className="mb-4 p-3 bg-green-50 border border-green-200 text-green-600 rounded-lg text-xs font-medium">{successMessage}</div>}
              {error && <div className="mb-4 p-3 bg-red-50 border border-red-200 text-red-600 rounded-lg text-xs font-medium">{error}</div>}

              <form onSubmit={handlePasswordOrRegisterSubmit} className="flex flex-col gap-4">
                <div>
                  <label className="block text-[12.5px] font-semibold text-inkSoft mb-1.5">User ID</label>
                  <input
                    type="text"
                    value={userId}
                    onChange={(e) => setUserId(e.target.value)}
                    placeholder="demo.user"
                    disabled={loading}
                    className="w-full border-[1.5px] border-line rounded-lg px-3.5 py-3 text-[14.5px] bg-bg focus:outline-none focus:border-brandBlue focus:shadow-[0_0_0_4px_rgba(47,102,144,0.12)] transition-all disabled:opacity-50"
                  />
                </div>

                {formMode === "register" && (
                  <div>
                    <label className="block text-[12.5px] font-semibold text-inkSoft mb-1.5">Email Address</label>
                    <input
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="teamalpha817@gmail.com"
                      disabled={loading}
                      className="w-full border-[1.5px] border-line rounded-lg px-3.5 py-3 text-[14.5px] bg-bg focus:outline-none focus:border-brandBlue focus:shadow-[0_0_0_4px_rgba(47,102,144,0.12)] transition-all disabled:opacity-50"
                    />
                  </div>
                )}

                <div>
                  <label className="block text-[12.5px] font-semibold text-inkSoft mb-1.5">Password</label>
                  <input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                    disabled={loading}
                    className="w-full border-[1.5px] border-line rounded-lg px-3.5 py-3 text-[14.5px] bg-bg focus:outline-none focus:border-brandBlue focus:shadow-[0_0_0_4px_rgba(47,102,144,0.12)] transition-all disabled:opacity-50"
                  />
                </div>

                <button
                  type="submit"
                  disabled={loading}
                  className="mt-2 inline-flex items-center justify-center rounded-full bg-ink px-6 py-3 text-sm font-semibold text-white hover:-translate-y-0.5 hover:shadow-[0_10px_20px_-8px_rgba(16,34,46,0.4)] transition-all disabled:opacity-50"
                >
                  {loading ? (formMode === "login" ? "Verifying..." : "Creating...") : (formMode === "login" ? "Verify Password" : "Create Account")}
                </button>
              </form>

              <div className="mt-5 text-center border-t border-line pt-4">
                <button
                  type="button"
                  onClick={() => {
                    setFormMode(formMode === "login" ? "register" : "login");
                    setError("");
                    setSuccessMessage("");
                  }}
                  className="text-[12.5px] font-semibold text-brandBlue hover:text-brandBlue/80 transition-colors"
                >
                  {formMode === "login" ? "Don't have an account? Sign up" : "Already have an account? Log in"}
                </button>
              </div>

              {formMode === "login" && cloudAuthMode === "none" && (
                <div className="mt-6 border-t border-line pt-5 flex flex-col gap-3">
                  <p className="text-center text-[12.5px] font-medium text-inkSoft mb-2">Or log in with your cloud provider</p>
                  <button 
                    type="button" 
                    onClick={() => setCloudAuthMode("aws")} 
                    className="w-full flex items-center justify-center gap-2 border-[1.5px] border-line rounded-lg px-4 py-2.5 text-sm font-semibold text-ink hover:bg-bg transition-colors"
                  >
                    Log in with AWS
                  </button>
                  <button 
                    type="button" 
                    onClick={() => setCloudAuthMode("gcp")} 
                    className="w-full flex items-center justify-center gap-2 border-[1.5px] border-line rounded-lg px-4 py-2.5 text-sm font-semibold text-ink hover:bg-bg transition-colors"
                  >
                    Log in with GCP
                  </button>
                  <button 
                    type="button" 
                    onClick={() => setCloudAuthMode("azure")} 
                    className="w-full flex items-center justify-center gap-2 border-[1.5px] border-line rounded-lg px-4 py-2.5 text-sm font-semibold text-ink hover:bg-bg transition-colors"
                  >
                    Log in with Azure
                  </button>
                </div>
              )}

              {formMode === "login" && cloudAuthMode !== "none" && (
                <div className="mt-6 border-t border-line pt-5">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-sm font-semibold text-ink">Authenticate with {cloudAuthMode.toUpperCase()}</h3>
                    <button type="button" onClick={() => { setCloudAuthMode("none"); setError(""); }} className="text-xs text-inkSoft hover:text-ink">Cancel</button>
                  </div>
                  <form onSubmit={handleCloudLoginSubmit} className="flex flex-col gap-4">
                    {cloudAuthMode === "aws" && (
                      <div>
                        <label className="block text-[12.5px] font-semibold text-inkSoft mb-1.5">IAM Role ARN</label>
                        <input type="text" value={awsRoleArn} onChange={e => setAwsRoleArn(e.target.value)} placeholder="arn:aws:iam::123456789012:role/CloudCareRole" className="w-full border-[1.5px] border-line rounded-lg px-3.5 py-2.5 text-[14.5px] bg-bg focus:outline-none focus:border-brandBlue focus:shadow-[0_0_0_4px_rgba(47,102,144,0.12)] transition-all" />
                      </div>
                    )}
                    {cloudAuthMode === "gcp" && (
                      <div>
                        <label className="block text-[12.5px] font-semibold text-inkSoft mb-1.5">Service Account JSON</label>
                        <textarea value={gcpJson} onChange={e => setGcpJson(e.target.value)} placeholder='{"type": "service_account", ...}' rows={3} className="w-full border-[1.5px] border-line rounded-lg px-3.5 py-2.5 text-[12px] font-mono bg-bg focus:outline-none focus:border-brandBlue focus:shadow-[0_0_0_4px_rgba(47,102,144,0.12)] transition-all" />
                      </div>
                    )}
                    {cloudAuthMode === "azure" && (
                      <>
                        <div>
                          <label className="block text-[12.5px] font-semibold text-inkSoft mb-1.5">Tenant ID</label>
                          <input type="text" value={azureTenantId} onChange={e => setAzureTenantId(e.target.value)} placeholder="Enter Tenant ID" className="w-full border-[1.5px] border-line rounded-lg px-3.5 py-2.5 text-[14.5px] bg-bg focus:outline-none focus:border-brandBlue focus:shadow-[0_0_0_4px_rgba(47,102,144,0.12)] transition-all" />
                        </div>
                        <div>
                          <label className="block text-[12.5px] font-semibold text-inkSoft mb-1.5">Client ID</label>
                          <input type="text" value={azureClientId} onChange={e => setAzureClientId(e.target.value)} placeholder="Enter Client ID" className="w-full border-[1.5px] border-line rounded-lg px-3.5 py-2.5 text-[14.5px] bg-bg focus:outline-none focus:border-brandBlue focus:shadow-[0_0_0_4px_rgba(47,102,144,0.12)] transition-all" />
                        </div>
                      </>
                    )}
                    <button type="submit" disabled={loading} className="w-full inline-flex items-center justify-center rounded-lg bg-brandBlue px-4 py-2.5 text-sm font-semibold text-white hover:bg-brandBlue/90 transition-all disabled:opacity-50">
                      {loading ? "Authenticating..." : `Connect ${cloudAuthMode.toUpperCase()}`}
                    </button>
                  </form>
                </div>
              )}

              {formMode === "login" && (
                <p className="text-center text-[12.5px] text-inkFaint mt-4">
                  Demo Credentials: <strong>demo.user</strong> / <strong>password123</strong>
                </p>
              )}
            </>
          )}

          {/* STEP 2: EMAIL OTP */}
          {step === "otp" && (
            <>
              <h1 className="font-display text-xl font-semibold text-ink mb-1">Enter Verification Code</h1>
              <p className="text-sm text-inkSoft mb-6">We've sent a 6-digit OTP code to your registered email.</p>

              {error && <div className="mb-4 p-3 bg-red-50 border border-red-200 text-red-600 rounded-lg text-xs font-medium">{error}</div>}

              <form onSubmit={handleOtpSubmit} className="flex flex-col gap-4">
                <div>
                  <div className="flex justify-between items-center mb-1.5">
                    <label className="block text-[12.5px] font-semibold text-inkSoft">Verification Code</label>
                    <span className={`text-[12px] font-mono ${timer < 60 ? "text-red-500 font-bold animate-pulse" : "text-brandBlue"}`}>
                      Expires in: {formatTime(timer)}
                    </span>
                  </div>
                  <input
                    type="text"
                    maxLength={6}
                    value={otp}
                    onChange={(e) => setOtp(e.target.value.replace(/\D/g, ""))}
                    placeholder="000000"
                    disabled={loading || timer === 0}
                    className="w-full text-center tracking-[8px] font-mono border-[1.5px] border-line rounded-lg px-3.5 py-3 text-lg bg-bg focus:outline-none focus:border-brandBlue focus:shadow-[0_0_0_4px_rgba(47,102,144,0.12)] transition-all disabled:opacity-50"
                  />
                </div>
                
                <button
                  type="submit"
                  disabled={loading || timer === 0}
                  className="mt-2 inline-flex items-center justify-center rounded-full bg-ink px-6 py-3 text-sm font-semibold text-white hover:-translate-y-0.5 hover:shadow-[0_10px_20px_-8px_rgba(16,34,46,0.4)] transition-all disabled:opacity-50"
                >
                  {loading ? "Validating..." : "Verify Code"}
                </button>
              </form>

              <div className="mt-5 flex items-center justify-between border-t border-line pt-4">
                <button
                  type="button"
                  onClick={() => setStep("password")}
                  disabled={loading}
                  className="text-[12.5px] font-medium text-inkSoft hover:text-ink transition-colors disabled:opacity-50"
                >
                  ← Back to password
                </button>

                <button
                  type="button"
                  onClick={handleResendOtp}
                  disabled={loading || resendCooldown > 0}
                  className="text-[12.5px] font-semibold text-brandBlue hover:text-brandBlue/80 transition-colors disabled:opacity-50 disabled:text-inkFaint"
                >
                  {resendCooldown > 0 ? `Resend in ${resendCooldown}s` : "Resend code"}
                </button>
              </div>
            </>
          )}

          {/* STEP 3: WEBAUTHN */}
          {step === "webauthn" && (
            <>
              <h1 className="font-display text-xl font-semibold text-ink mb-1">Device Biometrics</h1>
              <p className="text-sm text-inkSoft mb-6">Complete authentication using your device security (Face ID, Touch ID, Windows Hello, or PIN).</p>

              {error && <div className="mb-4 p-3 bg-red-50 border border-red-200 text-red-600 rounded-lg text-xs font-medium">{error}</div>}

              <div className="flex flex-col gap-4">
                <div className="p-4 bg-bg border border-line rounded-lg flex flex-col items-center justify-center text-center">
                  <span className="w-12 h-12 rounded-full bg-brandBlue/10 flex items-center justify-center mb-3">
                    <svg className="w-6 h-6 text-brandBlue" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 11c0 3.517-1.009 6.799-2.753 9.571m-3.44-2.04l.054-.09A13.916 13.916 0 009 11.571V11a7.002 7.002 0 00-7-7 2 2 0 00-2 2v.09C0 9.201 1.009 12.483 2.753 15.255m11.547-11.34A14.28 14.28 0 0113.123 12m-2.91-2.91A8.995 8.995 0 008 11.571V12a4 4 0 004 4h.09A13.978 13.978 0 0013 12V11c0-2.28-.94-4.34-2.457-5.83Z" />
                    </svg>
                  </span>
                  <p className="text-xs font-semibold text-ink">
                    {webauthnMode === "register" ? "Enroll Device Passkey" : 
                     webauthnMode === "authenticate" ? "Verifying Fingerprint/Face/PIN" : 
                     webauthnMode === "unsupported" ? "Passkey Not Supported" : "Biometrics Action Needed"}
                  </p>
                  <p className="text-[11px] text-inkSoft mt-1">
                    {webauthnMode === "register" ? "You will be prompted to create a credential on this browser." :
                     webauthnMode === "authenticate" ? "Please follow your browser's prompt to verify." :
                     webauthnMode === "unsupported" ? "This browser doesn't support platform WebAuthn." :
                     "Please trigger the ceremony again or use the fallback."}
                  </p>
                </div>

                {webauthnMode !== "unsupported" && (
                  <button
                    type="button"
                    onClick={() => triggerWebAuthn(tempToken, nextWebauthnStatus)}
                    disabled={loading}
                    className="inline-flex items-center justify-center rounded-full bg-ink px-6 py-3 text-sm font-semibold text-white hover:-translate-y-0.5 hover:shadow-[0_10px_20px_-8px_rgba(16,34,46,0.4)] transition-all disabled:opacity-50"
                  >
                    {loading ? "Waiting for device..." : "Retry Biometrics"}
                  </button>
                )}

                {/* Graceful fallbacks so we never hit a dead end */}
                <div className="border-t border-line pt-4 flex flex-col gap-2.5">
                  <button
                    type="button"
                    onClick={handleBypassWebAuthn}
                    disabled={loading}
                    className="w-full inline-flex items-center justify-center rounded-full border-[1.5px] border-line px-5 py-2.5 text-xs font-semibold text-inkSoft hover:bg-bg transition-all"
                  >
                    Bypass Biometrics (Demo Fallback)
                  </button>

                  <button
                    type="button"
                    onClick={() => setStep("password")}
                    disabled={loading}
                    className="w-full text-center text-xs text-inkFaint hover:text-inkSoft transition-colors"
                  >
                    Start over
                  </button>
                </div>
              </div>
            </>
          )}

        </div>

        <p className="text-center text-[13px] text-inkFaint mt-6">
          <Link href="/" className="hover:text-brandBlue transition-colors">
            ← Back to home
          </Link>
        </p>
      </div>
    </main>
  );
}
