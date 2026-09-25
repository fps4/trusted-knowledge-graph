/** @type {import('next').NextConfig} */
const nextConfig = {
  // A self-contained server bundle for the image (docker/web/Dockerfile).
  output: 'standalone',
  reactStrictMode: true,
  poweredByHeader: false,
};

export default nextConfig;
