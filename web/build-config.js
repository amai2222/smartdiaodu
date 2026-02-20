// 构建时根据环境变量生成 config.js，供 Cloudflare Pages 等注入变量。
// 使用：在 Cloudflare Pages 配置 SUPABASE_URL、SUPABASE_ANON_KEY、API_BASE（可选），Build 命令设为 node web/build-config.js
"use strict";
var fs = require("fs");
var path = require("path");
var supabaseUrl = process.env.SUPABASE_URL || "";
var supabaseAnonKey = process.env.SUPABASE_ANON_KEY || "";
var apiBase = process.env.API_BASE || "";
var out = path.join(__dirname, "config.js");
var js = "// Generated at build time from env\nwindow.SMARTDIAODU_CONFIG=" + JSON.stringify({
  supabaseUrl: supabaseUrl,
  supabaseAnonKey: supabaseAnonKey,
  apiBase: apiBase
}, null, 2) + ";\n";
fs.writeFileSync(out, js, "utf8");
console.log("Wrote " + out);
