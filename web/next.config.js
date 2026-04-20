/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: 'standalone',
  images: {
    // Allow serving PFD images from the API container
    remotePatterns: [
      { protocol: 'http', hostname: 'localhost', port: '8000' },
      { protocol: 'http', hostname: 'api' },
    ],
    unoptimized: true,
  },
};

module.exports = nextConfig;
