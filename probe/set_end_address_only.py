# -*- coding: utf-8 -*-
"""
分步测试：仅设置哈啰目的地为指定地址。
逻辑与出发地一致：点击目的地行(clEndAddress) → 两个输入框(城市+详细地址) → 点第一个搜索结果。
目的地行：序号 66 可点 [81,510]-[999,683] 中心(540,596)，见 车主页控件说明.md。
用法：TANZI_DRIVER_DEST=上海市浦江镇地铁站  python probe/set_end_address_only.py
"""
import os
import re
import subprocess
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
ADDRESS = os.environ.get("TANZI_DRIVER_DEST", "").strip() or "上海市浦江镇地铁站"


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


def click_first_search_result(d, detail, adb_fn, dump_keywords_and_patterns):
    """
    等待搜索结果后点击列表第一项。
    dump_keywords_and_patterns: (keywords_tuple, [(pattern, desc), ...]) 用于 dump 回退。
    """
    time.sleep(3)
    clicked = False
    # 方式 1：精确匹配常见第一个结果标题（目的地如 浦江镇地铁站）
    for kw in ("浦江镇", "地铁站", "浦江镇地铁站"):
        if kw not in detail:
            continue
        el = d(textContains=kw, instance=0)
        if el.exists(timeout=2):
            # 排除 EditText，优先 TextView（列表项）
            t = d(className="android.widget.TextView", textContains=kw, instance=0)
            if t.exists(timeout=1):
                t.click()
                print("  已点击第一个结果（TextView 含「%s」）" % kw)
            else:
                el.click()
                print("  已点击第一个结果（含「%s」）" % kw)
            clicked = True
            break
    if not clicked and len(detail) >= 2:
        el = d(className="android.widget.TextView", textContains=detail[:2], instance=0)
        if el.exists(timeout=2):
            el.click()
            print("  已点击第一个结果（TextView 含「%s」）" % detail[:2])
            clicked = True
    if not clicked:
        # 方式 2：dump 取第一个结果 bounds
        cmd = ["adb"] + (["-s", DEVICE] if DEVICE else []) + ["shell", "uiautomator", "dump", "/sdcard/window_dump.xml"]
        subprocess.run(cmd, capture_output=True, timeout=10)
        cmd2 = ["adb"] + (["-s", DEVICE] if DEVICE else []) + ["pull", "/sdcard/window_dump.xml", os.path.join(_script_dir, "window_dump.xml")]
        subprocess.run(cmd2, capture_output=True, timeout=10)
        dump_path = os.path.join(_script_dir, "window_dump.xml")
        if os.path.isfile(dump_path):
            with open(dump_path, "r", encoding="utf-8", errors="ignore") as f:
                xml = f.read()
            keywords, patterns = dump_keywords_and_patterns
            for pat in patterns:
                m = re.search(pat, xml)
                if m:
                    x1, y1 = int(m.group(1)), int(m.group(2))
                    x2, y2 = int(m.group(3)), int(m.group(4))
                    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                    if y1 < 800:
                        continue
                    adb_fn("shell", "input", "tap", str(cx), str(cy))
                    print("  已通过 bounds 点击第一个结果，坐标 (%d, %d)" % (cx, cy))
                    clicked = True
                    break
            if not clicked and keywords:
                for kw in keywords:
                    if kw not in detail:
                        continue
                    for m in re.finditer(r'text="[^"]*' + re.escape(kw) + r'[^"]*"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml):
                        y1 = int(m.group(2))
                        if y1 < 800:
                            continue
                        x1, x2, y2 = int(m.group(1)), int(m.group(3)), int(m.group(4))
                        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                        adb_fn("shell", "input", "tap", str(cx), str(cy))
                        print("  已通过 bounds 点击（%s），坐标 (%d, %d)" % (kw, cx, cy))
                        clicked = True
                        break
                    if clicked:
                        break
    if not clicked:
        for btn in ("确定", "搜索", "完成", "确认"):
            b = d(text=btn)
            if b.exists(timeout=1):
                b.click()
                print("  已点击 [%s]" % btn)
                break
    time.sleep(1)


def main():
    print("=== 分步设置目的地 ===")
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
        print("[步骤 0] 请先打开哈啰并进入车主页。")
        return 1
    print("[步骤 1] 当前包名: com.jingyao.easybike")

    print("[步骤 2] 确保在车主页（目的地行可见）…")
    end_el = d(resourceId="com.jingyao.easybike:id/clEndAddress")
    if not end_el.exists(timeout=3):
        print("  未找到目的地控件 clEndAddress，请先进入哈啰车主页。")
        return 1

    print("[步骤 3] 点击目的地行，打开地址栏…")
    end_el.click()
    print("  已点击，等待地址页加载 4 秒…")
    time.sleep(4)

    city, detail = split_city_and_detail(ADDRESS)
    print("[步骤 4] 两个输入框：城市=%s，详细地址=%s" % (city, detail))
    if not city and not detail:
        print("  地址解析失败。")
        return 1
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

    print("[步骤 5] 等待搜索结果，点击列表第一项…")
    # 目的地常见结果关键词与 dump 正则（浦江镇地铁站 等）
    dump_keywords = ("浦江镇", "地铁站", "浦江")
    dump_patterns = [
        r'text="浦江镇地铁站"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
        r'text="[^"]*浦江镇[^"]*"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
    ]
    click_first_search_result(d, detail, adb, (dump_keywords, dump_patterns))
    depart_time = os.environ.get("TANZI_DRIVER_DEPART_TIME", "").strip() or None
    confirm_departure_time_dialog(d, target_time=depart_time)

    print("\n完成。请查看手机目的地是否已变为:", ADDRESS[:24], "…")
    return 0


if __name__ == "__main__":
    sys.exit(main())
