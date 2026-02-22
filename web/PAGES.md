# 前端页面接入说明

所有需要「已登录」才能访问的页面，统一走鉴权脚本 `auth.js`，避免各页自己写 token/session 判断导致行为不一致（如点设置被要求重新登录）。

## 1. 统一鉴权（auth.js）

- **职责**：判断是否已登录（localStorage 的 `smartdiaodu_token` 或 Supabase `getSession()`），未登录则跳转登录页；已登录则先执行 `loadAppConfig` 再执行你传入的回调。
- **登录页责任**：登录成功后必须写入 `localStorage.setItem("smartdiaodu_token", access_token 或 "1")`，这样任意新页面只要用 `requireAuth` 即可，不会再出现「有 session 但没 token 被踢去登录」的问题。

## 2. 新增「需登录」页面的标准写法

### 2.1 脚本引入顺序（在 HTML 里）

```html
<script src="config.js"></script>
<!-- 其他样式、Tailwind 等 -->
<script src="https://unpkg.com/@supabase/supabase-js@2"></script>
<script src="index-config.js"></script>
<script src="index-state.js"></script>   <!-- 若不需要控制台状态可省略 -->
<script src="auth.js"></script>
<script src="你的业务.js"></script>
```

### 2.2 业务脚本里

```javascript
(function () {
  "use strict";
  var C = window.SmartDiaoduConsole;
  if (!C) {
    if (window.SmartDiaoduAuth) window.SmartDiaoduAuth.redirectToLogin();
    else window.location.replace("login.html");
    return;
  }

  function run() {
    // 已登录且 loadAppConfig 已执行，可安全使用 C.getApiBase()、C.getDriverId()、C.getSupabaseClient() 等
  }

  if (window.SmartDiaoduAuth && typeof window.SmartDiaoduAuth.requireAuth === "function") {
    window.SmartDiaoduAuth.requireAuth(run);
  } else {
    C.loadAppConfig(run); // 无 auth.js 时的兜底
  }
})();
```

### 2.3 可选：Supabase 被拦截时的提示

若页面希望像首页一样在「跟踪防护拦截 Supabase」时展示提示，可传 `onBlocked`：

```javascript
window.SmartDiaoduAuth.requireAuth(run, {
  onBlocked: function () {
    // 展示「Supabase 连接异常，请关闭跟踪防护或换浏览器」等
  }
});
```

### 2.4 自定义登录页地址

```javascript
window.SmartDiaoduAuth.requireAuth(run, { loginUrl: "my-login.html" });
```

## 3. 现有页面

| 页面 | 鉴权方式 |
|------|----------|
| index.html | auth.js → requireAuth(run, { onBlocked: showSupabaseBlockedNotice }) |
| setup.html | auth.js → requireAuth(loadDriverPlateThenRun) |
| login.html | 不鉴权；登录成功后写入 token（见 login.html 内脚本） |
| map.html | 在 iframe 内由 index 打开，不单独鉴权 |

以后新增的需登录页面，按「2. 新增需登录页面的标准写法」接入即可，不会再遇到「点进新页面被要求重新登录」的问题。
