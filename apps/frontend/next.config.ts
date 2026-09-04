import path from "node:path";

import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // The monorepo root and apps/web both carry their own lockfile — pin
  // Next's workspace root to this app so it doesn't guess wrong.
  outputFileTracingRoot: path.join(import.meta.dirname),
};

export default nextConfig;
