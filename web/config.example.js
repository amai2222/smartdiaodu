// 复制为 config.js 并填入实际值；勿提交 config.js（已加入 .gitignore）。
// Cloudflare Pages：用环境变量生成 config.js，无需在页面写明文。
window.SMARTDIAODU_CONFIG = {
  supabaseUrl: "",      // 例如 process.env.SUPABASE_URL 或 "https://xxx.supabase.co"
  supabaseAnonKey: "",  // 例如 process.env.SUPABASE_ANON_KEY 或 "eyJ..."
  apiBase: ""           // 可选，例如 process.env.API_BASE 或 "https://api.xxx.com"
};

// ---------- Cloudflare Pages 配置 ----------
// 1. 项目 Settings → Environment variables 添加（Production/Preview 按需）：
//    SUPABASE_URL         = https://你的项目.supabase.co
//    SUPABASE_ANON_KEY    = 你的 anon public key
//    API_BASE             = https://你的后端地址（可选）
// 2. Build 配置：
//    Build command:       node web/build-config.js
//    Build output dir:    web
// 构建时会根据上述变量生成 web/config.js，页面通过 <script src="config.js"></script> 读取。
