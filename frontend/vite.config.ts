import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';
import { loadEnv } from 'vite';

const dependency = (name: string) => fileURLToPath(new URL(`./node_modules/${name}`, import.meta.url));

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', 'VITE_');
  return {
    plugins: [react()],
    resolve: {
      alias: {
        react: dependency('react'),
        'react-dom': dependency('react-dom'),
        'react-router-dom': dependency('react-router-dom'),
        '@testing-library/react': dependency('@testing-library/react'),
        '@testing-library/user-event': dependency('@testing-library/user-event'),
        '@testing-library/jest-dom': dependency('@testing-library/jest-dom'),
      },
    },
    server: {
      port: 5173,
      host: '0.0.0.0',
      fs: {
        allow: ['..'],
      },
      proxy: {
        '/api': {
          target: env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000',
          changeOrigin: true,
        },
      },
    },
    test: {
      include: ['../tests/frontend/**/*.test.{ts,tsx}'],
      environment: 'jsdom',
      setupFiles: '../tests/frontend/setup.ts',
      css: true,
    },
  };
});
