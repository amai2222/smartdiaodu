# -*- coding: utf-8 -*-
"""解析 uiautomator dump，列出所有有 bounds 的控件，并生成示意图。"""
import re
import sys
import os

path = sys.argv[1] if len(sys.argv) > 1 else "window_dump.xml"
out_dir = os.path.dirname(os.path.abspath(path))
with open(path, "r", encoding="utf-8") as f:
    s = f.read()

def get_attr(attrs, name):
    m = re.search(r'\s' + re.escape(name) + r'="([^"]*)"', attrs)
    return m.group(1) if m else ""

# 匹配 <node ... /> 或 <node ...></node>，只取开标签内的属性
node_pattern = re.compile(r'<node\s+([^>]+?)(?:\s*/>|>)')
nodes = []
for m in node_pattern.finditer(s):
    attrs = m.group(1)
    bounds = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', attrs)
    if not bounds:
        continue
    x1, y1 = int(bounds.group(1)), int(bounds.group(2))
    x2, y2 = int(bounds.group(3)), int(bounds.group(4))
    w, h = x2 - x1, y2 - y1
    # 过滤太小的（可能是装饰）或无意义的
    if w < 5 or h < 5:
        continue
    text = get_attr(attrs, "text")
    desc = get_attr(attrs, "content-desc")
    rid = get_attr(attrs, "resource-id")
    clazz = get_attr(attrs, "class")
    clickable = "clickable=\"true\"" in attrs
    nodes.append({
        "bounds": (x1, y1, x2, y2),
        "text": text,
        "content-desc": desc,
        "resource-id": rid,
        "class": clazz.split(".")[-1] if clazz else "",
        "clickable": clickable,
    })

# 按 y 然后 x 排序
nodes.sort(key=lambda n: (n["bounds"][1], n["bounds"][0]))

# 只保留有文字、content-desc 或 resource-id 的，或面积较大的（可能是可点区域）
def meaningful(n):
    if n["text"] or n["content-desc"] or n["resource-id"]:
        return True
    x1, y1, x2, y2 = n["bounds"]
    return (x2 - x1) * (y2 - y1) >= 2000

filtered = [n for n in nodes if meaningful(n)]

# 输出列表
list_path = os.path.join(out_dir, "controls_list.txt")
with open(list_path, "w", encoding="utf-8") as f:
    f.write("序号\tbounds\tclickable\ttext\tcontent-desc\tresource-id\tclass\n")
    for i, n in enumerate(filtered):
        b = n["bounds"]
        bs = "[%d,%d][%d,%d]" % b
        t = (n["text"] or "")[:20]
        d = (n["content-desc"] or "")[:20]
        r = (n["resource-id"] or "").replace("com.jingyao.easybike:id/", "")
        c = "Y" if n["clickable"] else "N"
        f.write("%d\t%s\t%s\t%s\t%s\t%s\t%s\n" % (i, bs, c, t, d, r, n["class"]))
print("控件列表已写入:", list_path)
print("共 %d 个控件（有文字/描述/ID 或面积较大）\n" % len(filtered))

# 打印前 80 个到控制台
for i, n in enumerate(filtered[:80]):
    b = n["bounds"]
    cx, cy = (b[0] + b[2]) // 2, (b[1] + b[3]) // 2
    t = (n["text"] or n["content-desc"] or n["resource-id"] or "-")[:28]
    c = "可点" if n["clickable"] else ""
    print("%3d  [%4d,%4d][%4d,%4d]  中心(%4d,%4d)  %s  %s" % (i, b[0], b[1], b[2], b[3], cx, cy, t, c))

if len(filtered) > 80:
    print("\n... 还有 %d 个，见 %s" % (len(filtered) - 80, list_path))

# 生成简单示意图 HTML（按坐标画矩形，可点击看序号）
html_path = os.path.join(out_dir, "controls_diagram.html")
scale = 0.4
with open(html_path, "w", encoding="utf-8") as f:
    f.write("""<!DOCTYPE html><html><head><meta charset="utf-8"><title>车主页控件示意图</title>
<style>
body { font-family: sans-serif; margin: 12px; background: #1a1a1a; color: #eee; }
h2 { margin-bottom: 4px; }
#screen { position: relative; width: %dpx; height: %dpx; background: #333; border: 2px solid #666; }
.ctl { position: absolute; border: 1px solid rgba(100,200,255,0.8); background: rgba(100,200,255,0.15); 
  box-sizing: border-box; font-size: 10px; overflow: hidden; display: flex; align-items: center; justify-content: center;
  word-break: break-all; text-align: center; }
.ctl.clickable { border-color: rgba(100,255,100,0.9); background: rgba(100,255,100,0.2); }
.ctl:hover { background: rgba(255,200,100,0.35); }
.idx { position: absolute; left: 2px; top: 2px; font-weight: bold; color: #ffc; }
</style></head><body>
<h2>车主页控件示意图（比例 %.0f%%）</h2>
<p>绿色边框=可点击。悬停高亮。矩形内数字为序号，对应下方列表。</p>
<div id="screen">
""" % (1080 * scale, 2042 * scale, scale * 100))
    for i, n in enumerate(filtered):
        x1, y1, x2, y2 = n["bounds"]
        w, h = (x2 - x1) * scale, (y2 - y1) * scale
        if w < 2 or h < 2:
            continue
        left, top = x1 * scale, y1 * scale
        cls = "ctl clickable" if n["clickable"] else "ctl"
        label = (n["text"] or n["content-desc"] or n["resource-id"] or "").replace("com.jingyao.easybike:id/", "")
        if len(label) > 12:
            label = label[:11] + "…"
        f.write('  <div class="%s" style="left:%dpx;top:%dpx;width:%dpx;height:%dpx" title="%d %s">'
                '<span class="idx">%d</span> %s</div>\n' % (
            cls, left, top, w, h, i, label, i, label
        ))
    f.write("</div>\n<p><strong>序号 → 控件列表见 controls_list.txt，或运行本脚本时的控制台输出。</strong></p>\n</body></html>")
print("示意图已写入:", html_path)
