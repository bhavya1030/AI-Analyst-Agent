/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Required for production Docker image (multi-stage standalone server)
  output: "standalone",
};

export default nextConfig;
