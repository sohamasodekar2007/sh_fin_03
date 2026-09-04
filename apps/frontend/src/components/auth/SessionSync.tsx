"use client";

import { useEffect } from "react";
import { SessionProvider, useSession } from "next-auth/react";

import { setToken } from "@/lib/api";

/**
 * Copies the CloudCare access_token NextAuth's jwt/session callbacks
 * attached to the session (src/auth.ts, after POST /v1/auth/sso-callback)
 * into the same storage the credentials flow uses — see src/lib/api.ts's
 * setToken(). This is the one place the SSO path and the password+OTP
 * path converge into a single auth model for the rest of the app.
 */
function SsoTokenSync() {
  const { data: session, status } = useSession();

  useEffect(() => {
    if (status !== "authenticated") return;
    const token = (session as { cloudcareAccessToken?: string } | null)?.cloudcareAccessToken;
    if (token) setToken(token);
  }, [session, status]);

  return null;
}

export function SessionSync({ children }: { children: React.ReactNode }) {
  return (
    <SessionProvider>
      <SsoTokenSync />
      {children}
    </SessionProvider>
  );
}
