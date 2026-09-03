// ---------------------------------------------------------------------------
// Bearer-token helper for direct browser -> FastAPI calls (spec section 2).
// Session state itself lives in NextAuth (useSession()/signOut() from
// "next-auth/react") — this only fetches the raw JWT NextAuth signed
// (via app/api/auth/token/route.ts) so client components can attach it as
// `Authorization: Bearer <token>` on calls to NEXT_PUBLIC_API_BASE_URL.
// ---------------------------------------------------------------------------

let cachedToken: string | null = null;
let cachedAt = 0;
const TOKEN_CACHE_MS = 30_000; // NextAuth re-signs hourly; a short client cache avoids a round trip per fetch

export async function getAuthHeaders(): Promise<Record<string, string>> {
  const now = Date.now();
  if (!cachedToken || now - cachedAt > TOKEN_CACHE_MS) {
    try {
      const res = await fetch("/api/auth/token");
      const data = await res.json();
      cachedToken = data.token ?? null;
      cachedAt = now;
    } catch {
      cachedToken = null;
    }
  }
  return cachedToken ? { Authorization: `Bearer ${cachedToken}` } : {};
}
