import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    react(),
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
