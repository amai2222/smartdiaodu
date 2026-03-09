# -*- coding: utf-8 -*-
import re
import sys
fp = sys.argv[1] if len(sys.argv) > 1 else "window_dump.xml"
with open(fp, "r", encoding="utf-8", errors="ignore") as f:
    s = f.read()
for name in ["text", "content-desc"]:
    for m in re.finditer(name + '="([^"]+)"', s):
        t = m.group(1).strip()
        if not t or len(t) < 2:
            continue
        if "车主" in t or "顺风" in t or "大厅" in t or "乘客" in t:
            print(name, t[:50])
