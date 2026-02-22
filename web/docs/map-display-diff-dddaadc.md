# 地图在移动端显示：dddaadc 与当前差异

## 一、commit dddaadc 时（能打开地图）的逻辑

### 1. index.html 地图入口与加载
- **无** viewSetup，设置是 `<a href="setup.html">` 整页跳转。
- **无** 地图 iframe 预加载：`mapFrame` 初始 `src="about:blank"`，只有用户点「地图」时才在 `showMap()` 里执行 `mapFrame.src = "map.html"; mapLoaded = true`。
- **showMap() 顺序**：先设 `mapFrame.src = "map.html"`，再 `viewMap.classList.remove("hidden")`，即先开始加载再显示视图（几乎同时）。
- **addTap**：仅 `click` + `touchend`（preventDefault + fn），无 touchstart/pointerdown。
- **无** postMessage 通知地图页「可见」。

### 2. map.css（当时）
```css
html, body { margin: 0; padding: 0; height: 100%; width: 100%; min-height: 100vh; overflow: hidden; ... }
#map { position: absolute; top: 0; left: 0; right: 0; bottom: 0; width: 100%; height: 100%; min-height: 300px; z-index: 0; background: #1a1a2e; touch-action: pan-x pan-y pinch-zoom; }
```
- `#map` 使用 **position: absolute**，依赖 html/body 的 `height: 100%` 形成高度链。
- 有 **min-height: 300px** 兜底。

### 3. map-init.js（当时）
- 无 `resize` / `message` / `visibilitychange` 监听。
- 无 iframe 内 800ms/2500ms 延迟 `invalidateSize`。
- 仅 init 后 200ms 调用一次 `invalidateSize()`。

### 4. index.css 的 viewMap（当时）
- `#viewMap.app-view { position: absolute; inset: 0; background: #0c0c0f; }`
- `#viewMap.app-view .w-full { height: 100%; }`
- 无 `min-height: 50vh`。

---

## 二、当前（黑屏）与之的差异

| 项目 | dddaadc（能打开） | 当前（黑屏） |
|------|-------------------|--------------|
| 地图加载时机 | 仅点「地图」时设 `mapFrame.src`，无预加载 | 已改回「点地图再加载」，一致 |
| #map 定位 | `position: absolute` + top/left/right/bottom 0 | `position: fixed` + `100vw` / `100vh` / `100dvh` |
| #map 尺寸 | `width/height: 100%`，`min-height: 300px` | 无 right/bottom，无 min-height |
| html/body 高度 | `height: 100%`，`min-height: 100vh` | `height: 100vh`，`height: 100dvh` |
| 地图页事件 | 仅 init 后 200ms invalidateSize | + resize / postMessage / visibilitychange / 800ms、2500ms 兜底 |

**关键推断**：当时在 Safari 下能打开，是因为  
1）地图 iframe **从未在隐藏状态下加载**，一点「地图」才加载，iframe 已有正确尺寸；  
2）`#map` 用 **absolute + 100% 高**，在 iframe 内依赖 body 高度链即可撑满；  
3）有 **min-height: 300px** 防止高度为 0。  

当前改为 **fixed + 100dvh** 后，在部分 Safari/iframe 环境下若视口或 dvh 计算异常，仍可能得到 0 或错误高度，导致黑屏。

---

## 三、建议修复（对齐当时可用的显示逻辑）

- **map.css**：恢复 `#map` 为 **position: absolute** + top/left/right/bottom: 0 + width/height: 100% + **min-height: 300px**；html/body 恢复 **height: 100%** 与 **min-height: 100vh**（可保留 100dvh 作为增强，但以 100% 为主）。
- **保持**「点地图再加载」、不预加载地图 iframe。
- 保留 resize/postMessage/visibilitychange 等重绘逻辑作为补充，不影响「先能亮屏」的主路径。
