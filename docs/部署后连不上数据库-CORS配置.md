# 部署到自有域名后连不上数据库

站点部署在自有域名（如 `https://diaodu.325218.xyz`）时，若控制台一直显示「暂无乘客」「4 个空座」，按下面顺序排查。

---

## 1. 你现在在「API Keys」页——密钥用对即可

- 你截图里是 **Settings → API Keys**，这里**没有 CORS**，是正常的。
- 前端（浏览器）只用 **Publishable key**（`sb_publishable_...` 那段），不要用 Secret key。
- 在 **config.js** 里把 `supabaseAnonKey` 设成当前项目 **Publishable key** 的完整内容（复制「default」那条 Publishable key 即可）。
- 若 config 里已经是 `sb_publishable_StKwGU9ceIC_7CNXzB3muQ_JNJhfqp0` 且和后台一致，密钥就没问题。

---

## 2. CORS 在哪里（新版本可能没有单独入口）

- 左侧栏 **Project Settings** 下可能有 **API**（不是「API Keys」），点进去看有没有 **CORS / Allowed origins**。
- 或点 **Configuration → Data API**，看是否有 CORS / 允许来源 等设置。
- **若整站都找不到 CORS 配置**：Supabase 的 Data API 默认允许浏览器跨域，很多项目不需要改 CORS。连不上更可能是下面 3、4。

---

## 3. 确认 config.js 在线上能被读到

- 部署后浏览器访问：`https://你的域名/config.js`，应能打开且内容里有 `supabaseUrl`、`supabaseAnonKey`。
- 若 404 或内容不对，说明 **config.js 没部署或没同源**，页面拿不到地址和密钥，就会「未连接数据库」。

**若用 Cloudflare Pages：**  
`config.js` 在仓库里被 .gitignore，不会随 Git 推送。需要在**构建时**用环境变量生成：
1. **Build command** 填：`node web/build-config.js`
2. **Build output directory** 填：`web`
3. 在 **Settings → Environment variables** 里添加：`SUPABASE_URL`、`SUPABASE_ANON_KEY`，以及可选 `API_BASE`、`BAIDU_MAP_AK`、`DRIVER_ID`
4. 保存后 **Retry deployment**，等构建完成再访问 `https://你的域名/config.js` 检查。  
详见：[Cloudflare_Pages_部署与_GitHub_自动更新.md](./Cloudflare_Pages_部署与_GitHub_自动更新.md)

---

## 4. 网络与浏览器

- 本机或网络是否拦截了 `*.supabase.co`（公司防火墙、代理、DNS）。
- 关掉会改请求的浏览器扩展，或用无痕/换浏览器再试。
- 控制台里 **webextension.js** 报错（如 `Cannot read properties of null (reading '1')`）多半是**浏览器扩展**注入的脚本出的错，不是本站代码。可禁用扩展或用无痕模式验证。

---

## 小结

| 现象 | 先做 |
|------|------|
| 找不到 CORS 配置 | 正常，很多项目不用改；先确认 Publishable key 和 config.js 一致、config.js 线上可访问。 |
| 密钥 | 用 **Publishable key**，和 config 里 `supabaseAnonKey` 一致。 |
| 仍连不上 | 查 F12 报错、确认 config.js 能加载、换网络/浏览器试。 |
