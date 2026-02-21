# 后端 API 用同一域名 HTTPS（路径反代）

域名 xg.325218.xyz 和证书已经用在 80/443 上时，**不必给 88 端口单独配证书**。在现有 443 的 Nginx 配置里加一个 **路径**，把 `/api/` 反代到本机 88，即可让 API 走 HTTPS、复用同一张证书。

---

## 思路

- **现有**：`https://xg.325218.xyz`（443）和 `http://xg.325218.xyz`（80）照常给现有站点用。
- **新增**：`https://xg.325218.xyz/api/` → 反代到本机 `http://127.0.0.1:88/`（你的智能调度后端）。
- 前端 `apiBase` 填：`https://xg.325218.xyz/api`（不要末尾斜杠）。

这样地图页（HTTPS）请求 `https://xg.325218.xyz/api/current_route_preview` 不会被混合内容拦截，且证书和域名都是现成的。

---

## Nginx 配置示例

在**已经监听 443 且配置了 xg.325218.xyz 证书**的 `server` 里增加一个 `location`：

```nginx
server {
    listen 443 ssl;
    server_name xg.325218.xyz;
    # 你现有的 ssl_certificate、ssl_certificate_key 等不变
    # ...

    # 现有站点（根路径等）的 location 保持不变
    location / {
        # 你原来的反代或 root 等
    }

    # 智能调度 API：/api/ 反代到本机 88
    location /api/ {
        proxy_pass http://127.0.0.1:88/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

要点：

- `location /api/` 与 `proxy_pass http://127.0.0.1:88/` 末尾的斜杠配合，会把 `/api/xxx` 转成后端的 `/xxx`（例如 `/api/current_route_preview` → `/current_route_preview`）。
- 无需给 88 端口单独配 SSL，也无需改 88 上的服务。

---

## 前端配置

- **config.js** 或 Cloudflare 环境变量 **API_BASE** 设为：`https://xg.325218.xyz/api`
- 不要写成 `https://xg.325218.xyz/api/`（末尾不要斜杠），因为前端会自己拼路径，如 `apiBase + "/current_route_preview"`。

---

## 按你现有配置的改法

在你 443 的 `server` 里，在 **`location /8d0bbc7e1f/` 这一段后面**加下面这一整块（只新增 `location /api/`，其余不变）：

```nginx
	location /8d0bbc7e1f/
        {
        proxy_redirect off;
	proxy_pass http://127.0.0.1:23640;
        proxy_http_version 1.1;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $http_host;
        proxy_set_header Early-Data $ssl_early_data;
        }

	# 智能调度 API：/api/ 反代到本机 88
	location /api/ {
		proxy_pass http://127.0.0.1:88/;
		proxy_http_version 1.1;
		proxy_set_header Host $host;
		proxy_set_header X-Real-IP $remote_addr;
		proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
		proxy_set_header X-Forwarded-Proto $scheme;
	}
}
```

改完后执行 `nginx -t` 检查语法，再 `nginx -s reload` 或 `systemctl reload nginx`。前端 apiBase 填 `https://xg.325218.xyz/api` 即可。

---

## 验证

```bash
curl -s -o /dev/null -w "%{http_code}" https://xg.325218.xyz/api/health
```

若后端有 `/health`，返回 200 即表示反代和证书都正常。然后在控制台/地图页把 apiBase 改成上述地址，刷新即可。

---

## 为什么 http://129.226.191.86:88/ 打不开？

- **88 和 8000 是两回事**：脚本 `smartdiaodu.py` 用 uvicorn 只监听 **8000**；**88** 一般是你在本机用 **Nginx** 监听的端口，再反代到 `127.0.0.1:8000`。所以「88 打不开」要先看 88 上有没有服务在听。
- **排查**：  
  1. 本机执行 `curl -s http://127.0.0.1:8000/`，若返回 `{"service":"...","status":"ok"}` 说明后端正常（脚本已提供 `GET /` 和 `GET /health`）。  
  2. 若 8000 正常但 88 打不开，说明 **Nginx 没在 88 监听** 或没反代到 8000。在 Nginx 里给 88 端口加一个 server（或在你现有 80/443 的 server 里用 `location /api/` 反代到 8000，见上文），并 `listen 88;`、`proxy_pass http://127.0.0.1:8000;`。  
- **根路径**：后端已提供 `GET /` 和 `GET /health`，访问 `http://IP:88/` 或 `https://xg.325218.xyz/api/` 会返回 JSON，不再 404。
