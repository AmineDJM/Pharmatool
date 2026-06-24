/** @type {import('next').NextConfig} */
const nextConfig = {
  // Lint is enforced in CI/locally, not as a hard gate on the production build.
  eslint: { ignoreDuringBuilds: true },
};

export default nextConfig;
