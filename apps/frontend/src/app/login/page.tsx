import { LoginForm } from "./LoginForm";

/**
 * Server component: reads the SSO provider env vars (server-only, so this
 * can't happen in a "use client" file) and passes down whether each is
 * actually configured. src/auth.ts registers Google and GitHub
 * unconditionally, so without this check the buttons in LoginForm would
 * send an unconfigured user straight into NextAuth's own
 * /api/auth/error page instead of failing inside our UI.
 */
export default function LoginPage() {
  return (
    <LoginForm
      googleEnabled={Boolean(process.env.AUTH_GOOGLE_ID && process.env.AUTH_GOOGLE_SECRET)}
      githubEnabled={Boolean(process.env.AUTH_GITHUB_ID && process.env.AUTH_GITHUB_SECRET)}
    />
  );
}
