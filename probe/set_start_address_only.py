# -*- coding: utf-8 -*-
"""
分步测试：仅设置哈啰出发地为指定地址。
哈啰地址页有两个输入框：第 1 个是城市（如 南通市、上海市），第 2 个是详细地址。
步骤：1 确保哈啰在前台 → 2 点击车主 → 3 点击出发地打开地址栏 → 4 城市框填市、详细地址框填街道等 → 5 点击确定。
用法：TANZI_DRIVER_LOC=江苏省南通市如东县掘港街道荣生豪景花苑  python probe/set_start_address_only.py
"""
import os
import re
import sys
import time

_script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _script_dir)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(_script_dir), ".env"))
except ImportError:
    pass
try:
    from helo_address_helpers import split_city_and_detail, confirm_departure_time_dialog
except ImportError:
    def split_city_and_detail(full_address):
        s = (full_address or "").strip()
        if not s:
            return ("", "")
        m = re.search(r"([\u4e00-\u9fff]+市)", s)
        if m:
            city = m.group(1)
            idx = s.find(city) + len(city)
            detail = s[idx:].strip()
            return (city, detail)
        return (s, "")
    def confirm_departure_time_dialog(d):
        return False

DEVICE = os.environ.get("TANZI_DEVICE", "").strip()
ADDRESS = os.environ.get("TANZI_DRIVER_LOC", "").strip() or "江苏省南通市如东县掘港街道荣生豪景花苑"

try:
    import uiautomator2 as u2
    U2 = True
except ImportError:
    u2 = None
    U2 = False


def adb(*args):
    import subprocess
    cmd = ["adb"] + (["-s", DEVICE] if DEVICE else []) + list(args)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=15)


def main():
    print("=== 分步设置出发地 ===")
    print("目标地址:", ADDRESS)
    print("设备:", DEVICE or "默认")
    print("uiautomator2:", "可用" if U2 else "未安装")
    print()

    if not U2:
        print("请安装 uiautomator2: pip install uiautomator2")
        return 1

    d = u2.connect(DEVICE) if DEVICE else u2.connect()
    pkg = (d.app_current() or {}).get("package", "")
    if pkg != "com.jingyao.easybike":
        print("[步骤 0] 启动哈啰…")
        adb("shell", "am", "start", "-a", "android.intent.action.MAIN", "-c", "android.intent.category.LAUNCHER", "-p", "com.jingyao.easybike")
        for _ in range(15):
            time.sleep(1)
            pkg = (d.app_current() or {}).get("package", "")
            if pkg == "com.jingyao.easybike":
                print("  哈啰已到前台。")
                time.sleep(2)
                break
        else:
            print("  等待超时，请手动打开哈啰到车主页后重试。")
    print("[步骤 1] 当前包名:", (d.app_current() or {}).get("package"))

    print("[步骤 2] 进入车主页…")
    # 若已在车主页（出发地控件已存在）则跳过
    start_el = d(resourceId="com.jingyao.easybike:id/clStartAddress")
    if start_el.exists(timeout=2):
        print("  已在车主页（出发地控件已可见），跳过点「车主」。")
    else:
        if d(text="车主").exists(timeout=2):
            d(text="车主").click()
            print("  已点击「车主」。")
        elif d(textContains="车主").exists(timeout=2):
            d(textContains="车主").click()
            print("  已点击「车主」。")
        else:
            print("  未找到「车主」；若已在车主页请忽略。")
        time.sleep(2)

    print("[步骤 3] 点击出发地，打开地址栏…")
    start_el = d(resourceId="com.jingyao.easybike:id/clStartAddress")
    if not start_el.exists(timeout=3):
        print("  未找到出发地控件 clStartAddress，请手动切到哈啰车主页后再运行。")
        return 1
    start_el.click()
    print("  已点击，等待地址页加载 4 秒…")
    time.sleep(4)

    city, detail = split_city_and_detail(ADDRESS)
    print("[步骤 4] 两个输入框：城市=%s，详细地址=%s" % (city, detail))
    if not city and not detail:
        print("  地址解析失败。")
        return 1
    # 第 1 个输入框：城市（南通市 / 上海市 等）
    edit_city = d(className="android.widget.EditText", instance=0)
    edit_detail = d(className="android.widget.EditText", instance=1)
    if not edit_city.exists(timeout=3):
        print("  未找到第 1 个输入框（城市）。")
        return 1
    edit_city.click()
    time.sleep(0.3)
    edit_city.set_text(city)
    print("  第 1 个输入框（城市）已填: %s" % city)
    time.sleep(0.5)
    if edit_detail.exists(timeout=2):
        edit_detail.click()
        time.sleep(0.3)
        edit_detail.set_text(detail)
        print("  第 2 个输入框（详细地址）已填: %s" % (detail[:20] + "…" if len(detail) > 20 else detail))
    else:
        print("  未找到第 2 个输入框，仅填了城市。")
    time.sleep(3)

    print("[步骤 5] 等待搜索结果，点击列表第一项…")
    clicked = False
    # 方式 1：精确匹配第一个结果标题（列表里是「荣生·豪景花苑」），且排除 EditText
    for exact in ("荣生·豪景花苑", "荣生·豪景花苑(西南门)", "荣生·豪景花苑(东北1门)"):
        el = d(text=exact)
        if el.exists(timeout=1):
            el.click()
            print("  已点击第一个结果（精确: %s）" % exact)
            clicked = True
            break
    if not clicked:
        # 方式 2：用 TextView 含关键词（避免点到输入框），取 instance=0 为列表中第一个
        for kw in ("荣生·豪景花苑", "荣生", "豪景花苑"):
            if kw not in detail:
                continue
            # 只点 TextView，不点 EditText
            el = d(className="android.widget.TextView", textContains=kw, instance=0)
            if el.exists(timeout=2):
                el.click()
                print("  已点击第一个结果（TextView 含「%s」）" % kw)
                clicked = True
                break
    if not clicked:
        # 方式 3：dump 取第一个结果行的 bounds，用 adb tap 点击
        import subprocess
        cmd = ["adb"] + (["-s", DEVICE] if DEVICE else []) + ["shell", "uiautomator", "dump", "/sdcard/window_dump.xml"]
        subprocess.run(cmd, capture_output=True, timeout=10)
        cmd2 = ["adb"] + (["-s", DEVICE] if DEVICE else []) + ["pull", "/sdcard/window_dump.xml", os.path.join(_script_dir, "window_dump.xml")]
        subprocess.run(cmd2, capture_output=True, timeout=10)
        dump_path = os.path.join(_script_dir, "window_dump.xml")
        if os.path.isfile(dump_path):
            with open(dump_path, "r", encoding="utf-8", errors="ignore") as f:
                xml = f.read()
            # 找第一个包含「荣生·豪景花苑」或「南通市城东路」的 node（非 EditText），取 bounds
            for pattern in [
                r'class="android\.widget\.TextView"[^>]*text="荣生·豪景花苑"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
                r'text="荣生·豪景花苑"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
                r'text="南通市城东路1-8号"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
            ]:
                m = re.search(pattern, xml)
                if m:
                    x1, y1 = int(m.group(1)), int(m.group(2))
                    x2, y2 = int(m.group(3)), int(m.group(4))
                    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                    adb("shell", "input", "tap", str(cx), str(cy))
                    print("  已通过 bounds 点击第一个结果，坐标 (%d, %d)" % (cx, cy))
                    clicked = True
                    break
            if not clicked:
                # 最后一个备选：任意 bounds 含「荣生」的节点，取 Y 最小的（最靠上）
                for m in re.finditer(r'text="[^"]*荣生[^"]*"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml):
                    y1 = int(m.group(2))
                    if y1 < 800:  # 排除顶部搜索区
                        continue
                    x1, x2, y2 = int(m.group(1)), int(m.group(3)), int(m.group(4))
                    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                    adb("shell", "input", "tap", str(cx), str(cy))
                    print("  已通过 bounds 点击（荣生），坐标 (%d, %d)" % (cx, cy))
                    clicked = True
                    break
    if not clicked:
        print("  未找到第一个结果，尝试点「确定」…")
        for btn in ("确定", "搜索", "完成", "确认"):
            b = d(text=btn)
            if b.exists(timeout=1):
                b.click()
                print("  已点击 [%s]" % btn)
                break
    time.sleep(1)
    depart_time = os.environ.get("TANZI_DRIVER_DEPART_TIME", "").strip() or None
    confirm_departure_time_dialog(d, target_time=depart_time)

    print("\n完成。请查看手机出发地是否已变为:", ADDRESS[:24], "…")
    return 0


if __name__ == "__main__":
    sys.exit(main())
