# -*- coding: utf-8 -*-
"""单独测试 uiautomator2 能否找到并点击哈啰出发地。先确保哈啰在前台且为车主页，再运行。"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
except ImportError:
    pass

DEVICE = os.environ.get("TANZI_DEVICE", "").strip()
import uiautomator2 as u2

def main():
    print("连接设备:", DEVICE or "默认")
    d = u2.connect(DEVICE) if DEVICE else u2.connect()
    print("连接成功，当前包名:", d.app_current().get("package"))
    # 找出发地
    sel = d(resourceId="com.jingyao.easybike:id/clStartAddress")
    print("clStartAddress exists:", sel.exists(timeout=2))
    if sel.exists(timeout=2):
        print("执行 click() ...")
        sel.click()
        print("click() 已调用，请看手机是否弹出地址栏。")
    else:
        print("未找到 clStartAddress，尝试 textContains 出发 ...")
        for t in ["出发", "你将从"]:
            s = d(textContains=t)
            if s.exists(timeout=1):
                print("  found:", t, "count:", len(s))
                s.click()
                print("  已点击，请看手机。")
                return
        print("未找到可点控件。")

if __name__ == "__main__":
    main()
