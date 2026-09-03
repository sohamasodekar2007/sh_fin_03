import { NextResponse } from "next/server";
import bcrypt from "bcryptjs";
import { randomUUID } from "crypto";
import { getUsersCollection } from "@/lib/mongodb";

// Manual sign-up for NextAuth's CredentialsProvider (spec section 2,
// "fallback Manual Authentication... protected by bcrypt password
// hashing"). OAuth users never hit this route — they're auto-provisioned
// by FastAPI on first JWT sight (apps/api/dependencies.py).
export async function POST(req: Request) {
  const { email, password, full_name } = await req.json();

  if (!email || !password || password.length < 8) {
    return NextResponse.json({ detail: "Email and an 8+ character password are required." }, { status: 400 });
  }

  const users = await getUsersCollection();
  const existing = await users.findOne({ email });
  if (existing) {
    return NextResponse.json({ detail: "An account with this email already exists." }, { status: 409 });
  }

  const hashed_password = await bcrypt.hash(password, 12);
  await users.insertOne({
    id: randomUUID(),
    tenant_id: "demo-tenant",
    email,
    full_name: full_name || null,
    image: null,
    provider: "credentials",
    provider_account_id: null,
    hashed_password,
    created_at: new Date().toISOString(),
  });

  return NextResponse.json({ status: "created" }, { status: 201 });
}
