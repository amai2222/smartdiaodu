# -*- coding: utf-8 -*-
import re
import sys
path = sys.argv[1] if len(sys.argv) > 1 else "window_dump.xml"
with open(path, "r", encoding="utf-8") as f:
    s = f.read()

# 找 bounds= 在 node 内，提取 resource-id / text / bounds
bounds_re = re.compile(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"')
for node in re.finditer(r'<node[^>]+>', s):
    tag = node.group(0)
    if "StartAddress" in tag or "StartPoint" in tag or "你将从" in tag or "出发" in tag:
        bid = bounds_re.search(tag)
        b = (" [%s,%s][%s,%s]" % bid.groups()) if bid else ""
        # 简化：只打 resource-id 或 text
        rid = re.search(r'resource-id="([^"]+)"', tag)
        tx = re.search(r'text="([^"]*)"', tag)
        cl = "clickable=" in tag and "clickable=\"true\"" in tag
        print((rid.group(1) if rid else "") or (tx.group(1) if tx else ""), b, "clickable", cl)
