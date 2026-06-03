/** @type {import('next').NextConfig} */
const path = require('path');

const backendApiUrl = process.env.BACKEND_API_URL || 'http://127.0.0.1:8100';

const nextConfig = {
  reactStrictMode: true,
  allowedDevOrigins: ['localhost', '127.0.0.1'],
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
