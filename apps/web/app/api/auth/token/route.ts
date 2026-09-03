import { NextResponse } from "next/server";
import { getToken } from "next-auth/jwt";

// Hands the browser the raw, compact HS256 JWT NextAuth just signed (see
// lib/auth-options.ts's custom jwt.encode) so client components can attach
// it as `Authorization: Bearer <token>` on direct calls to the FastAPI
// backend — apps/api/security.py decodes this exact token, no separate
// backend-specific token exists.
export async function GET(req: Request) {
  const raw = await getToken({
    req: req as unknown as Parameters<typeof getToken>[0]["req"],
    secret: process.env.NEXTAUTH_SECRET,
    raw: true,
  });

  if (!raw) {
    return NextResponse.json({ token: null }, { status: 401 });
  }
  return NextResponse.json({ token: raw });
}
