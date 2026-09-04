import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { SESSION_COOKIE_NAME } from "@/lib/api";

/**
 * /dashboard, /onboarding and /approvals require a session; /login and /
 * are public. Middleware only ever checks for the PRESENCE of the session
 * cookie (see src/lib/api.ts's setToken) — it never reads or validates the
 * JWT itself, since middleware runs on the Edge runtime and the actual
 * bearer token is attached per-request by src/lib/api.ts on the client.
 * The backend is still the real authority: an expired/forged token simply
 * gets a 401 from the API, same as any other client.
 */

const PROTECTED_PREFIXES = ["/dashboard", "/onboarding", "/approvals"];

function isProtected(pathname: string): boolean {
  return PROTECTED_PREFIXES.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));
}

export function middleware(request: NextRequest) {
  const { pathname, search } = request.nextUrl;

  if (!isProtected(pathname)) {
    return NextResponse.next();
  }

  const hasSession = Boolean(request.cookies.get(SESSION_COOKIE_NAME)?.value);
  if (hasSession) {
    return NextResponse.next();
  }

  const loginUrl = new URL("/login", request.url);
  loginUrl.searchParams.set("returnTo", `${pathname}${search}`);
  return NextResponse.redirect(loginUrl);
}

export const config = {
  matcher: ["/dashboard/:path*", "/onboarding/:path*", "/approvals/:path*"],
};
