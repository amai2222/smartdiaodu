// 构建时根据环境变量生成 config.js，供 Cloudflare Pages 等注入变量。
// 使用：在 Cloudflare Pages 配置 SUPABASE_URL、SUPABASE_ANON_KEY、API_BASE（可选），Build 命令设为 node web/build-config.js
"use strict";
var fs = require("fs");
var path = require("path");
var supabaseUrl = process.env.SUPABASE_URL || "";
var supabaseAnonKey = process.env.SUPABASE_ANON_KEY || "";
var apiBase = process.env.API_BASE || "https://xg.325218.xyz/api";
var baiduMapAk = process.env.BAIDU_MAP_AK || "W5IBbZpLZwYgEhpmeINcv5d8JqLtX1iG";
var driverId = process.env.DRIVER_ID || "";
var out = path.join(__dirname, "config.js");
var js = "// Generated at build time from env. Do not edit in repo.\nwindow.SMARTDIAODU_CONFIG=" + JSON.stringify({
  supabaseUrl: supabaseUrl,
  supabaseAnonKey: supabaseAnonKey,
  apiBase: apiBase,
  baiduMapAk: baiduMapAk,
  driverId: driverId
}, null, 2) + ";\n";
fs.writeFileSync(out, js, "utf8");
console.log("Wrote " + out);
