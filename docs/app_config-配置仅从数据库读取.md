# 应用配置仅从数据库读取（app_config）

除**连接数据库**所需的参数外，前端与后端均从表 **app_config** 读取配置。

- **前端**：Supabase URL、Anon Key 仍来自 config.js / 登录后 localStorage；**api_base、baidu_map_ak、driver_id** 仅从 DB 读。
- **后端**：SUPABASE_URL、SUPABASE_SERVICE_ROLE_KEY、JWT_SECRET 仍从环境变量读；**其余**（百度 AK、Bark、模式与超时等）启动时从 app_config 读，未读到则用代码内默认值。

---

## 表结构

```sql
-- 见 supabase/migrations/012_app_config.sql
CREATE TABLE app_config (
  key text PRIMARY KEY,
  value text NOT NULL DEFAULT ''
);
```

前端用：`api_base`、`baidu_map_ak`、`driver_id`（见 012）；可选 `baidu_map_ak_browser`（网页端地图底图专用，见 014）。若未配 `baidu_map_ak_browser` 则用 `baidu_map_ak`。  
后端用：**`baidu_ak_server`**（服务器端百度 AK，地理编码/路线，见 015）；未配置时回退到 `baidu_map_ak`。另加 `baidu_service_id`、`bark_key`、`driver_mode` 等（见 013）。前端地图底图只用 **`baidu_map_ak`**（网页端 AK）。  
RLS 允许 `public` 只读（SELECT）；后端用 SERVICE_ROLE 读。

---

## 修改配置

在 Supabase **SQL Editor** 或 **Table Editor** 中修改 `app_config` 表即可，例如：

```sql
UPDATE app_config SET value = 'https://你的API地址/api' WHERE key = 'api_base';
UPDATE app_config SET value = '你的百度地图AK' WHERE key = 'baidu_map_ak';
UPDATE app_config SET value = '司机UUID' WHERE key = 'driver_id';
```

前端在页面加载时会从该表拉取一次并缓存，刷新页面即生效。

---

## 仍从 config / 环境变量来的

- **前端**：Supabase URL、Anon Key 由 config.js 或登录后 localStorage 提供，不放入 app_config。
- **后端**：`SUPABASE_URL`、`SUPABASE_SERVICE_ROLE_KEY`、`JWT_SECRET` 由环境变量提供；启动时用它们连库并读取 app_config，其余配置仅从 DB 覆盖。
