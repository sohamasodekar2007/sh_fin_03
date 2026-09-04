import NextAuth from "next-auth";
import GitHub from "next-auth/providers/github";
import Google from "next-auth/providers/google";

/**
 * NextAuth v5 handles the Google/GitHub OAuth handshake only — it is NOT
 * the app's auth model. The `jwt` callback below exchanges the verified
 * OAuth profile for a real CloudCare JWT via the backend's
 * POST /v1/auth/sso-callback (apps/api/routers/auth.py), the same shape
 * password+OTP login returns. src/components/auth/SsoTokenSync.tsx then
 * copies that token into the same storage (localStorage + a readable
 * cookie for middleware.ts) the credentials flow already uses — see
 * src/lib/api.ts's setToken(). One auth model for the rest of the app,
 * regardless of which of the two login paths produced it.
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Only register a provider once it's actually configured — requesting an
// unconfigured provider is what produces NextAuth's own raw
// "Server error / problem with the server configuration" page
// (/api/auth/error). src/app/login/page.tsx also hides the corresponding
// button client-side; this is the server-side half of the same guard, so
// even a direct hit on /api/auth/signin/google fails safely.
const providers = [
  ...(process.env.AUTH_GOOGLE_ID && process.env.AUTH_GOOGLE_SECRET ? [Google] : []),
  ...(process.env.AUTH_GITHUB_ID && process.env.AUTH_GITHUB_SECRET ? [GitHub] : []),
];

export const { handlers, auth, signIn, signOut } = NextAuth({
  providers,
  session: { strategy: "jwt" },
  callbacks: {
    async jwt({ token, account, profile }) {
      // Only runs right after a fresh OAuth sign-in (account + profile are
      // only present on that first callback invocation, per NextAuth's own
      // contract) — every subsequent request just reuses the token below.
      if (account && profile?.email) {
        try {
          const res = await fetch(`${API_BASE_URL}/v1/auth/sso-callback`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              provider: account.provider,
              email: profile.email,
              name: profile.name ?? null,
              provider_account_id: account.providerAccountId,
            }),
          });
          if (res.ok) {
            const data = await res.json();
            token.cloudcareAccessToken = data.access_token as string;
            token.cloudcareTenantId = data.tenant_id as string;
            token.cloudcareUserId = data.user_id as string;
          } else {
            console.error("sso-callback failed", res.status, await res.text());
          }
        } catch (err) {
          // The OAuth session still exists even if the backend is
          // unreachable — the user just won't have API access until they
          // retry, rather than being locked out of the sign-in entirely.
          console.error("sso-callback unreachable", err);
        }
      }
      return token;
    },
    async session({ session, token }) {
      return {
        ...session,
        cloudcareAccessToken: token.cloudcareAccessToken as string | undefined,
        cloudcareTenantId: token.cloudcareTenantId as string | undefined,
        cloudcareUserId: token.cloudcareUserId as string | undefined,
      };
    },
  },
});
