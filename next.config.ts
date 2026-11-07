import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  experimental: { cpus: 1 },
  // Tailwind is processed by postcss.config.mjs for both development and production.
};

export default nextConfig;
