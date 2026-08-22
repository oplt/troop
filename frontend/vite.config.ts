import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

const DEV_SERVICE_WORKER_RESET = `
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    await self.registration.unregister();
    const cacheNames = await caches.keys();
    await Promise.all(cacheNames.map((cacheName) => caches.delete(cacheName)));
    const clients = await self.clients.matchAll({ type: "window" });
    await Promise.all(clients.map((client) => client.navigate(client.url)));
  })());
});
`

/** Replaces a production PWA worker that still controls the localhost Vite origin. */
function devServiceWorkerReset(): Plugin {
  return {
    name: 'troop-dev-service-worker-reset',
    apply: 'serve',
    configureServer(server) {
      server.middlewares.use((request, response, next) => {
        if (request.url?.split('?')[0] !== '/sw.js') {
          next()
          return
        }

        response.statusCode = 200
        response.setHeader('Content-Type', 'text/javascript; charset=utf-8')
        response.setHeader('Cache-Control', 'no-store')
        response.setHeader('Service-Worker-Allowed', '/')
        response.end(DEV_SERVICE_WORKER_RESET)
      })
    },
  }
}

export default defineConfig({
  plugins: [
    react(),
    devServiceWorkerReset(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: [],
      manifest: {
        name: 'Troop',
        short_name: 'Troop',
        description: 'AI-assisted orchestration and operational workflows.',
        theme_color: '#171A20',
        icons: []
      }
    })
  ],
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          react: ["react", "react-dom"],
          router: ["react-router-dom"],
          query: ["@tanstack/react-query"],
          forms: ["react-hook-form", "@hookform/resolvers", "zod"],
          mui: ["@mui/material", "@mui/icons-material", "@emotion/react", "@emotion/styled"],
          xyflow: ["@xyflow/react"],
        },
      },
    },
  },
})
