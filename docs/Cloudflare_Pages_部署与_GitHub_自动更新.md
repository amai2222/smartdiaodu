# 网页部署到 Cloudflare Pages + GitHub 自动更新

控制台（`web/` 下的静态页面）可部署到 **Cloudflare Pages**，并绑定 GitHub 仓库实现**推送即自动发布**。

---

## 部署清单（按顺序打勾）

- [ ] 代码已推送到 GitHub 仓库
- [ ] Cloudflare Dashboard → Workers & Pages → Create → Connect to Git → 选该仓库
- [ ] **Build command** 填：`node web/build-config.js`
- [ ] **Build output directory** 填：`web`
- [ ] **Settings → Environment variables** 添加：`SUPABASE_URL`、`SUPABASE_ANON_KEY`、`API_BASE`（可选）、`BAIDU_MAP_AK`（可选）、`DRIVER_ID`（可选）
- [ ] 保存后 **Save and Deploy** 或 **Retry deployment**，等构建完成
- [ ] 访问 `https://<项目名>.pages.dev/login.html`，用 Supabase 用户（如 admin@test.com / 123456）登录

---

## 一、前置条件

- 代码已在 **GitHub** 仓库中（可先只提交 `web/` 或整个项目）。
- 后端 API（`smartdiaodu.py`）单独运行在你自己的服务器或其它平台；网页里填的「API 地址」指向该后端即可。

---

## 二、Cloudflare Pages 部署步骤

### 1. 打开 Cloudflare Pages

1. 登录 [Cloudflare Dashboard](https://dash.cloudflare.com/)
2. 左侧选 **Workers & Pages**
3. 点击 **Create** → **Pages** → **Connect to Git**

### 2. 连接 GitHub

1. 选 **GitHub**，按提示授权 Cloudflare 访问你的 GitHub
2. 选择**存放本项目的仓库**（例如 `smartdiaodu`）
3. 点击 **Begin setup**

### 3. 配置构建设置（必须跑构建以注入环境变量）

| 配置项 | 建议值 | 说明 |
|--------|--------|------|
| **Production branch** | `main` | 推送到该分支会触发生产发布 |
| **Build command** | `node web/build-config.js` | 用环境变量生成 config.js，登录页才能读到 Supabase URL/密钥 |
| **Build output directory** | `web` | 部署的是 web 目录内容 |

- **Root directory** 保持默认（不填），即仓库根目录。
- 填好后先不要点 Deploy，先去下一步配环境变量，再回来点 **Save and Deploy**。

### 4. 配置环境变量（Variables and Secrets）

在 **Settings** → **Environment variables** 里为 **Production**（以及需要的 **Preview**）添加：

| 变量名 | 类型 | 说明 |
|--------|------|------|
| `SUPABASE_URL` | 纯文本 | Supabase 项目 URL，如 `https://xxx.supabase.co` |
| `SUPABASE_ANON_KEY` | 密钥 | Supabase 的 anon public key（Publishable key） |
| `API_BASE` | 纯文本（可选） | 后端 API 地址，如 `https://api.你的域名.com` 或 `http://129.226.191.86:88` |
| `BAIDU_MAP_AK` | 纯文本（可选） | 百度地图 AK，地图页用 |
| `DRIVER_ID` | 纯文本（可选） | 当前控制台默认司机 ID，与 seed 一致时可写死 |

- 配好后保存，然后到 **Deployments** 里对当前部署点 **Retry deployment**，或推送一次代码触发新部署，构建时才会把变量写进 config.js。

### 5. 得到访问地址

部署完成后会得到一个地址，形如：

- `https://<项目名>.pages.dev`

之后每次向 GitHub 的 **main** 分支推送，Cloudflare 会自动重新部署，几分钟内生效。

---

## 三、日常使用（自动更新）

1. 本地改完 `web/` 下文件后：
   ```bash
   git add web/
   git commit -m "更新控制台/登录页"
   git push origin main
   ```
2. 打开 Cloudflare Dashboard → **Workers & Pages** → 你的 Pages 项目，在 **Deployments** 里可看到新部署进度。
3. 部署完成后，访问 `https://<项目名>.pages.dev` 即为最新页面。

---

## 四、自定义域名（可选）

1. 在 Pages 项目里点 **Custom domains**
2. 添加你的域名（如 `console.yourdomain.com`）
3. 按提示在域名 DNS 里添加 CNAME 指向 `<项目名>.pages.dev`，或使用 Cloudflare 提供的 A/CNAME 记录

---

## 五、注意事项

- **API 地址**：由环境变量 `API_BASE` 在构建时写入 config，无需在页面里再填。
- **登录页**：访问 `/login.html` 登录；若希望根路径 `/` 直接打开登录页，在 **Settings → Builds & deployments** 里配置 **Redirects**：`/` → `/login.html`。
- **CORS**：后端 `smartdiaodu.py` 已允许任意来源，跨域请求无问题。
- **仅前端**：Cloudflare Pages 只托管静态文件；后端需单独部署（如 VPS 上跑 `smartdiaodu.py`）。

---

## 六、部署失败：Failed to publish your Function

若构建和资源上传都成功，最后出现：

```text
Error: Failed to publish your Function. Got error: Unknown internal error occurred.
```

说明是 **Cloudflare 侧在发布「Function」时出错**。本项目是纯静态（Build output = `web`），并未使用 Functions，该错误多为平台偶发或兼容性问题。

**建议按顺序尝试：**

1. **直接重试**  
   在 **Deployments** 里对该次部署点 **Retry deployment**，很多情况下再次部署会通过。

2. **关闭 Pages Functions（若可配）**  
   在 Pages 项目 **Settings** 中查看是否有与 **Functions**、**Workers** 或 **Compatibility** 相关的选项，若有「Enable Functions」之类，可尝试关闭，再重新部署。

3. **确认构建配置**  
   确保 **Build output directory** 为 `web`，且构建命令只生成静态文件（例如 `node web/build-config.js`），不要产出 `_worker.js` 或 `functions` 目录，避免被当成 Function 发布。

4. **仍失败时**  
   到 [Cloudflare Community](https://community.cloudflare.com/) 或 [workers-sdk Issues](https://github.com/cloudflare/workers-sdk/issues) 搜索 `Failed to publish your Function`，按最新讨论尝试；或联系 Cloudflare 支持（若为付费账户）。
