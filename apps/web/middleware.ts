import { withAuth } from "next-auth/middleware";

// Server-side route protection (closes the TODO the old dashboard page left
// behind: "protect this route server-side with middleware instead").
export default withAuth({
  pages: { signIn: "/login" },
});

export const config = {
  matcher: ["/dashboard/:path*", "/chat/:path*"],
};
