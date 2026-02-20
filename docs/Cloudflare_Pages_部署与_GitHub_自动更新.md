# 网页部署到 Cloudflare Pages + GitHub 自动更新

控制台（`web/` 下的静态页面）可部署到 **Cloudflare Pages**，并绑定 GitHub 仓库实现**推送即自动发布**。

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

### 3. 配置构建设置（静态站，无需构建）

| 配置项 | 建议值 | 说明 |
|--------|--------|------|
| **Production branch** | `main` | 推送到该分支会触发生产发布 |
| **Build command** | 留空，或填 `echo "static"` | 无构建步骤即可 |
| **Build output directory** | `web` | 项目里网页所在目录 |

- 若仓库根目录就是网页（没有 `web` 子目录），则 **Build output directory** 填 `./`。
- 填好后点 **Save and Deploy**，等第一次部署完成。

### 4. 得到访问地址

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

- **API 地址**：部署后打开控制台，在「设置」里填写你的**后端 API 地址**（例如 `https://api.yourdomain.com` 或你运行 `smartdiaodu.py` 的地址），否则接口请求会失败。
- **登录页**：若访问的是根路径，需在 Pages 里把**根目录设为 `web`**，这样访问 `/login.html`、`/index.html` 才会正确。若希望用根路径即打开登录页，可在 Pages 的 **Settings → Builds & deployments** 里配置 **Redirects**：`/` → `/login.html`（按需设置）。
- **CORS**：后端 `smartdiaodu.py` 已允许任意来源（`allow_origins=["*"]`），Cloudflare 上的页面跨域请求无问题。
- **仅前端**：Cloudflare Pages 只托管静态文件，不运行 Python；后端需单独部署（如 VPS、Railway、Render 等）。
