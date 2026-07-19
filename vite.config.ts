import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';

export default defineConfig({
  plugins: [vue()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined;
          if (id.includes('@icon-park')) return 'vendor-icons';
          if (id.includes('xterm')) return 'vendor-terminal';
          if (id.includes('marked')) return 'vendor-markdown';
          if (id.includes('vue')) return 'vendor-vue';
          return 'vendor';
        },
      },
    },
  },
});
