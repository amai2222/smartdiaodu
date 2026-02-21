# Nginx reload 报 invalid PID 的修复（自定义安装 + systemd）

当 Nginx 用**自定义路径**（如 `/etc/nginx/sbin/nginx -c /etc/nginx/conf/nginx.conf`）由 systemd 启动时，若 **ExecReload 没有带 `-c`**，reload 会读默认 PID 文件 `/var/run/nginx.pid`（空），导致：
- `nginx -s reload` → `invalid PID number "" in "/var/run/nginx.pid"`
- `systemctl reload nginx` → `Job for nginx.service failed`

**你当前情况**：ExecStart 有 `-c /etc/nginx/conf/nginx.conf`，ExecReload 没有，所以只需改 ExecReload。

---

## 直接修复（按你当前 nginx.service）

编辑服务，把 **ExecReload** 改成和 ExecStart 一样带 `-c`：

```bash
sudo systemctl edit --full nginx.service
```

在 `[Service]` 里找到这一行：
```ini
ExecReload=/etc/nginx/sbin/nginx -s reload
```
改成：
```ini
ExecReload=/etc/nginx/sbin/nginx -c /etc/nginx/conf/nginx.conf -s reload
```
保存退出后执行：
```bash
sudo systemctl daemon-reload
sudo systemctl reload nginx
```

若 `systemctl edit --full` 提示没有该 unit，则直接改文件：
```bash
sudo vi /etc/systemd/system/nginx.service
```
同样只改上述 **ExecReload** 那一行，保存后 `daemon-reload` 再 `reload nginx`。

---

## 1. 看当前 Nginx 用的 PID 文件路径（可选）

主配置里会有 `pid` 指令，例如：
```bash
grep -E "^\s*pid\s+" /etc/nginx/conf/nginx.conf
```
若在 `conf/` 下，可能是：
```bash
grep -r "pid " /etc/nginx/conf/
```
记下路径，例如 `/etc/nginx/logs/nginx.pid` 或 `logs/nginx.pid`（相对主配置目录）。

---

## 2. 确认该 PID 文件存在且为当前主进程

主进程 PID 可从 systemd 看到（如 `Main PID: 23078`），然后：
```bash
# 若 pid 在 /etc/nginx/logs/nginx.pid
cat /etc/nginx/logs/nginx.pid
# 应输出 23078（或你 status 里看到的 MAINPID）
```

---

## 3. 修 systemd 的 ExecReload（关键）

让 reload 和 start 用**同一份配置**，这样会读同一份 PID 文件。

编辑服务文件：
```bash
sudo systemctl edit --full nginx.service
```
或直接改（若存在）：
```bash
sudo vi /etc/systemd/system/nginx.service
```

找到 `ExecReload=` 这一行，改成**带 `-c` 指定配置**，例如：
```ini
ExecReload=/etc/nginx/sbin/nginx -c /etc/nginx/conf/nginx.conf -s reload
```
保存后执行：
```bash
sudo systemctl daemon-reload
sudo systemctl reload nginx
```

若你的 unit 里是 `ExecReload=/etc/nginx/sbin/nginx -s reload`（没有 `-c ...`），就按上面加上 `-c /etc/nginx/conf/nginx.conf`。

---

## 4. 以后重载配置

一律用：
```bash
sudo systemctl reload nginx
```
不要用 `nginx -s reload`（除非你显式执行 `/etc/nginx/sbin/nginx -c /etc/nginx/conf/nginx.conf -s reload`）。

---

## 5. 配置警告与 `unknown directive "http2"`（可选）

若 **nginx -t 报 `unknown directive "http2"`**：说明当前 Nginx 不支持独立写法 `http2 on;`。在 **v2ray.conf** 里：
- **删掉** 第 8 行左右的 `http2 on;`
- 把 `listen 443 ssl;` 和 `listen [::]:443 ssl;` 改回 **`listen 443 ssl http2`** 和 **`listen [::]:443 ssl http2`**
- 若改回后仍报 unknown directive，则去掉 http2，只保留 `listen 443 ssl`（站点仍可用，仅无 HTTP/2）

若只想去掉 warn、不报错，在 v2ray.conf 里只删或注释：`ssl_stapling on;`、`ssl_stapling_verify on;`、`ssl_early_data on;`，**不要** 改成 `http2 on`（除非你确认 Nginx 支持）。

改完后 `sudo systemctl reload nginx`。
