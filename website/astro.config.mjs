import { defineConfig } from 'astro/config';

// https://astro.build/config
export default defineConfig({
  // GitHub Pages 部署时通常使用仓库名作为 base，
  // 如需自定义域名或 user 站点，可在此调整。
  site: 'https://example.github.io',
  base: '/xinjiang-industry-info/',
  output: 'static',
});
