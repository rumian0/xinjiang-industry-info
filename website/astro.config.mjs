import { defineConfig } from 'astro/config';

// https://astro.build/config
export default defineConfig({
  // EdgeOne Pages 部署在根路径，base 设为 '/'。
  // site 用于生成 sitemap、canonical 等绝对地址，部署后请替换为实际域名。
  site: 'http://xj.mingcy.cn/',
  base: '/',
  output: 'static',
});
