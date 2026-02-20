// 复制为 config.js 并填入实际值；勿提交 config.js（已加入 .gitignore）。
// Cloudflare Pages：用环境变量生成 config.js，无需在页面写明文。
window.SMARTDIAODU_CONFIG = {
  supabaseUrl: "",
  supabaseAnonKey: "",
  apiBase: "",
  baiduMapAk: ""        // 可选，百度地图 AK（控制台「行程与地图」选百度地图时用），在 lbsyun.baidu.com 申请
};

// ---------- Cloudflare Pages 配置 ----------
// 1. 项目 Settings → Environment variables 添加（Production/Preview 按需）：
//    SUPABASE_URL         = https://你的项目.supabase.co
//    SUPABASE_ANON_KEY    = 你的 anon public key
//    API_BASE             = 你的后端地址（可选）
//    BAIDU_MAP_AK         = 百度地图 AK（可选，用于地图选「百度地图」）
// 2. Build 配置：
//    Build command:       node web/build-config.js
//    Build output dir:    web
// 构建时会根据上述变量生成 web/config.js，页面通过 <script src="config.js"></script> 读取。
