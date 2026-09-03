/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // PLACEHOLDER: if you deploy the backend separately (e.g. Render, Railway,
  // EC2), you can proxy /api/* calls to it during local dev by uncommenting:
  //
  // async rewrites() {
  //   return [
  //     {
  //       source: "/api/:path*",
  //       destination: `${process.env.NEXT_PUBLIC_API_BASE_URL}/:path*`,
  //     },
  //   ];
  // },
};

module.exports = nextConfig;
