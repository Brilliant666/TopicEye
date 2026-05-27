/** @type {import('next').NextConfig} */
const path = require('path');

const backendApiUrl = process.env.BACKEND_API_URL || 'http://localhost:8000';

const nextConfig = {
  reactStrictMode: true,
  turbopack: {
    root: path.resolve(__dirname),
  },
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${backendApiUrl}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
