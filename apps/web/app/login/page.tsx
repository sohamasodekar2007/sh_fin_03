"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { signIn } from "next-auth/react";

type FormMode = "login" | "register";

const OAUTH_PROVIDERS = [
  { id: "google", label: "Continue with Google" },
  { id: "github", label: "Continue with GitHub" },
  { id: "azure-ad", label: "Continue with Microsoft Entra ID" },
];

export default function LoginPage() {
  const router = useRouter();

  const [formMode, setFormMode] = useState<FormMode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setSuccessMessage("");

    if (!email || !password) {
      setError("Please enter your email and password.");
      return;
    }

    setLoading(true);
    try {
      if (formMode === "register") {
        const res = await fetch("/api/auth/register", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password, full_name: fullName }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Account registration failed.");
        setSuccessMessage("Account created — log in below.");
        setFormMode("login");
        setPassword("");
        return;
      }

      const result = await signIn("credentials", { email, password, redirect: false });
      if (result?.error) {
        throw new Error("Invalid email or password.");
      }
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
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

        <div className="bg-surface border border-line rounded-lg2 shadow-soft p-8">
          <h1 className="font-display text-xl font-semibold text-ink mb-1">
            {formMode === "login" ? "Welcome back" : "Create an account"}
          </h1>
          <p className="text-sm text-inkSoft mb-6">
            {formMode === "login" ? "Sign in to view your cloud cost dashboard." : "Sign up with email — or use SSO below."}
          </p>

          <div className="flex flex-col gap-2.5 mb-5">
            {OAUTH_PROVIDERS.map((provider) => (
              <button
                key={provider.id}
                type="button"
                onClick={() => signIn(provider.id, { callbackUrl: "/dashboard" })}
                className="w-full inline-flex items-center justify-center rounded-full border-[1.5px] border-line px-5 py-2.5 text-[13.5px] font-semibold text-ink hover:border-brandBlue hover:text-brandBlue transition-all"
              >
                {provider.label}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-3 mb-5">
            <span className="flex-1 h-px bg-line" />
            <span className="text-[11.5px] text-inkFaint font-medium">OR</span>
            <span className="flex-1 h-px bg-line" />
          </div>

          {successMessage && <div className="mb-4 p-3 bg-green-50 border border-green-200 text-green-600 rounded-lg text-xs font-medium">{successMessage}</div>}
          {error && <div className="mb-4 p-3 bg-red-50 border border-red-200 text-red-600 rounded-lg text-xs font-medium">{error}</div>}

          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            {formMode === "register" && (
              <div>
                <label className="block text-[12.5px] font-semibold text-inkSoft mb-1.5">Full name</label>
                <input
                  type="text"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  placeholder="Demo User"
                  disabled={loading}
                  className="w-full border-[1.5px] border-line rounded-lg px-3.5 py-3 text-[14.5px] bg-bg focus:outline-none focus:border-brandBlue focus:shadow-[0_0_0_4px_rgba(47,102,144,0.12)] transition-all disabled:opacity-50"
                />
              </div>
            )}

            <div>
              <label className="block text-[12.5px] font-semibold text-inkSoft mb-1.5">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.com"
                disabled={loading}
                className="w-full border-[1.5px] border-line rounded-lg px-3.5 py-3 text-[14.5px] bg-bg focus:outline-none focus:border-brandBlue focus:shadow-[0_0_0_4px_rgba(47,102,144,0.12)] transition-all disabled:opacity-50"
              />
            </div>

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
              {loading ? "Please wait…" : formMode === "login" ? "Log in" : "Create account"}
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
