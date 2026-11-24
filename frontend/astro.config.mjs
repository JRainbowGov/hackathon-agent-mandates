// @ts-check
import { defineConfig } from 'astro/config';
import node from '@astrojs/node';
import sentry from '@sentry/astro';
import tailwindcss from '@tailwindcss/vite';
import { NodePackageImporter } from 'sass';
import { fileURLToPath } from 'node:url';
import svelte from '@astrojs/svelte';
const port = 4321;

/* Served under a path prefix when PUBLIC_BASE_PATH is set at build time, e.g. /frontend (src/lib/paths.ts) */
const base = process.env.PUBLIC_BASE_PATH || '/';

// https://astro.build/config
export default defineConfig({
  base,
  server: { port: port, host: true },
  adapter: node({
    mode: 'standalone',
  }),
  output: 'server',
  integrations: [
    svelte(),
    // Uncomment if using Sentry
    /*
    sentry({
      environment: process.env.ENVIRONMENT,
      dsn: process.env.SENTRY_DSN?.replaceAll('"', ''),
      tracesSampleRate: 0,
      replaysSessionSampleRate: 0,
      replaysOnErrorSampleRate: 0,
      sourceMapsUploadOptions: {
        project: process.env.REPO,
        authToken: process.env.SENTRY_AUTH_TOKEN?.replaceAll('"', ''),
      },
    }),
    */
  ],
  vite: {
    plugins: [tailwindcss()],
    css: {
      lightningcss: {
        errorRecovery: true,
      },
      preprocessorOptions: {
        scss: {
          loadPaths: [fileURLToPath(new URL('./node_modules', import.meta.url))],
          importers: [new NodePackageImporter()],
        },
      },
    },
  },
});
