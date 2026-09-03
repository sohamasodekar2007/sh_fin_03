import type { NextAuthOptions } from "next-auth";
import GoogleProvider from "next-auth/providers/google";
import GitHubProvider from "next-auth/providers/github";
import AzureADProvider from "next-auth/providers/azure-ad";
import CredentialsProvider from "next-auth/providers/credentials";
import bcrypt from "bcryptjs";
import jwt from "jsonwebtoken";
import { getUsersCollection } from "@/lib/mongodb";

// ---------------------------------------------------------------------------
// SSO protocol (spec section 2): NextAuth is the sole identity authority —
// FastAPI never mints or verifies a password, it only decodes the JWT this
// file produces. NextAuth v4's *default* jwt.encode/decode produce an
// encrypted JWE, which python-jose (a JWS/JWS-only library) cannot read —
// so encode/decode below are overridden to sign a plain, standard HS256 JWS
// with NEXTAUTH_SECRET instead. This is the exact same secret duplicated
// into apps/api/.env as NEXTAUTH_SECRET, so apps/api/security.py's
// python-jose HS256 decode reads this token directly, with zero extra hop.
// ---------------------------------------------------------------------------

const secret = process.env.NEXTAUTH_SECRET as string;

export const authOptions: NextAuthOptions = {
  session: { strategy: "jwt", maxAge: 60 * 60 }, // 1 hour, matches apps/api's old jwt_expire_minutes default
  secret,

  providers: [
    GoogleProvider({
      clientId: process.env.GOOGLE_CLIENT_ID || "",
      clientSecret: process.env.GOOGLE_CLIENT_SECRET || "",
    }),
    GitHubProvider({
      clientId: process.env.GITHUB_CLIENT_ID || "",
      clientSecret: process.env.GITHUB_CLIENT_SECRET || "",
    }),
    AzureADProvider({
      clientId: process.env.AZURE_AD_CLIENT_ID || "",
      clientSecret: process.env.AZURE_AD_CLIENT_SECRET || "",
      tenantId: process.env.AZURE_AD_TENANT_ID || "common",
    }),
    CredentialsProvider({
      name: "Email and password",
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" },
      },
      async authorize(credentials) {
        if (!credentials?.email || !credentials.password) return null;

        const users = await getUsersCollection();
        const user = await users.findOne({ email: credentials.email, provider: "credentials" });
        if (!user?.hashed_password) return null;

        const valid = await bcrypt.compare(credentials.password, user.hashed_password);
        if (!valid) return null;

        return {
          id: user.id,
          email: user.email,
          name: user.full_name || user.email,
          image: user.image || null,
        };
      },
    }),
  ],

  callbacks: {
    async jwt({ token, account, user }) {
      if (account && user) {
        token.provider = account.provider;
        token.provider_account_id = account.providerAccountId || (user as { id?: string }).id;
      }
      return token;
    },
    async session({ session, token }) {
      if (session.user) {
        (session.user as { provider?: string }).provider = token.provider as string | undefined;
      }
      return session;
    },
  },

  jwt: {
    async encode({ token }) {
      if (!token) return "";
      return jwt.sign(
        {
          sub: token.sub,
          email: token.email,
          name: token.name,
          picture: token.picture,
          provider: token.provider || "credentials",
          provider_account_id: token.provider_account_id || token.sub,
        },
        secret,
        { algorithm: "HS256", expiresIn: "1h" }
      );
    },
    async decode({ token }) {
      if (!token) return null;
      try {
        return jwt.verify(token, secret, { algorithms: ["HS256"] }) as Record<string, unknown>;
      } catch {
        return null;
      }
    },
  },

  pages: {
    signIn: "/login",
  },
};
