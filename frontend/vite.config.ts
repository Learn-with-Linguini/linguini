import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'
import { siteFiles } from './vite/siteFiles.js'
import { previewRoutes } from './vite/previewRoutes.js'

// https://vite.dev/config/
export default defineConfig(({ mode, isSsrBuild }) => {
  const env = loadEnv(mode, process.cwd(), '')
  return {
    publicDir: isSsrBuild ? false : 'public',
    build: { manifest: !isSsrBuild },
    plugins: [
      react(),
      previewRoutes(),
      !isSsrBuild && siteFiles({
        siteUrl: env.VITE_SITE_URL || 'https://www.learnwithlinguini.com',
        indexNowKey: env.INDEXNOW_KEY,
        googleSiteVerification: env.GOOGLE_SITE_VERIFICATION,
        bingSiteVerification: env.BING_SITE_VERIFICATION,
      }),
    ],
  }
})
