# -*- coding: utf-8 -*-
"""
单独测试：只翻动日期列到「明天」，不选小时/分钟、不点确认。
适配三星 S10（1080x2280）等机型；会先找「今天」坐标再向上拖一行。
用法：先打开哈啰车主页，点击「出发时间」行弹出时间选择框，再运行本脚本；或先运行脚本，在倒计时内点击出发时间。
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
    import uiautomator2 as u2
except ImportError:
    print("请安装: pip install uiautomator2")
    sys.exit(1)

DEVICE = os.environ.get("TANZI_DEVICE", "").strip()


def adb(*args):
    cmd = ["adb"] + (["-s", DEVICE] if DEVICE else []) + list(args)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=15)


def main():
    print("仅测试：把日期列滚动到「明天」")
    d = u2.connect()

    # 若当前没有时间弹窗，先尝试点击出发时间行打开弹窗
    if not d(text="请选择预计出发时间").exists(timeout=1) and not d(textContains="预计出发时间").exists(timeout=1):
        if d(resourceId="com.jingyao.easybike:id/clStartTime").exists(timeout=2):
            d(resourceId="com.jingyao.easybike:id/clStartTime").click()
            print("  已点击出发时间行，等待弹窗…")
        else:
            print("  请先在手机哈啰车主页点击「出发时间」打开弹窗，5 秒内…")
            for i in range(5, 0, -1):
                print(i, end=" ", flush=True)
                time.sleep(1)
            print()
        for _ in range(10):
            time.sleep(0.5)
            if d(text="请选择预计出发时间").exists(timeout=0.5) or d(textContains="预计出发时间").exists(timeout=0.5):
                break
        time.sleep(0.5)

    if not d(text="请选择预计出发时间").exists(timeout=2) and not d(textContains="预计出发时间").exists(timeout=2):
        print("未检测到「请选择预计出发时间」弹窗，请先打开弹窗后再运行。")
        return 1
    time.sleep(1.2)  # 等弹窗内滚轮完全出现

    # 找到「今天」的坐标：先 u2 控件，再 dump 层级里搜 text 今天 的 bounds
    cx, cy, row_height = None, None, 100  # 拖一行用 100px，更容易让滚轮响应
    el_today = None
    for sel in [d(text="今天"), d(textContains="今天")]:
        if sel.exists(timeout=2):
            el_today = sel
            break
    if el_today is not None and el_today.exists(timeout=0.5):
        try:
            info = el_today.info
            b = info.get("bounds") if info else None
            left, top, right, bottom = None, None, None, None
            if isinstance(b, dict):
                left, top = b.get("left"), b.get("top")
                right, bottom = b.get("right"), b.get("bottom")
            elif isinstance(b, str):
                m = re.search(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", b) or re.search(r"(\d+),(\d+)-(\d+),(\d+)", b)
                if m:
                    g = [int(x) for x in m.groups()]
                    left, top, right, bottom = g[0], g[1], g[2], g[3]
            if left is not None and right is not None and top is not None and bottom is not None:
                cx = (left + right) // 2
                cy = (top + bottom) // 2
                row_height = max(bottom - top, 50)
                print("  「今天」中心: (%d, %d), 行高: %d" % (cx, cy, row_height))
        except Exception as e:
            print("  获取「今天」位置失败: %s" % e)
    if cx is None or cy is None:
        # 从 dump 里搜包含「今天」的 node 的 bounds
        try:
            xml = d.dump_hierarchy()
            for m in re.finditer(r'text="今天"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml):
                x1, y1, x2, y2 = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
                cx = (x1 + x2) // 2
                cy = (y1 + y2) // 2
                row_height = max(y2 - y1, 50)
                print("  dump 找到「今天」: (%d, %d), 行高: %d" % (cx, cy, row_height))
                break
            if cx is None:
                for m in re.finditer(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"[^>]*text="今天"', xml):
                    x1, y1, x2, y2 = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
                    cx = (x1 + x2) // 2
                    cy = (y1 + y2) // 2
                    row_height = max(y2 - y1, 50)
                    print("  dump 找到「今天」(反序): (%d, %d)" % (cx, cy))
                    break
        except Exception:
            pass
    if cx is None or cy is None:
        # 从 dump 取日期列 dayView 的 bounds，弹窗内滚轮才在正确位置
        try:
            xml = d.dump_hierarchy()
            m = re.search(r'resource-id="com\.jingyao\.easybike:id/dayView"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml)
            if not m:
                m = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"[^>]*resource-id="com\.jingyao\.easybike:id/dayView"', xml)
            if m:
                x1, y1, x2, y2 = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
                cx = (x1 + x2) // 2
                cy = (y1 + y2) // 2
                row_height = max((y2 - y1) // 3, 60)
                print("  dump 找到日期列 dayView 中心: (%d, %d), 行高: %d" % (cx, cy, row_height))
        except Exception:
            pass
    if cx is None or cy is None:
        try:
            w, h = d.window_size()
        except Exception:
            w, h = 1080, 2280
        cx = 265
        cy = 1719   # 根据 dump 弹窗 dayView [58,1574][471,1864] 中心
        print("  使用 dayView 默认中心(弹窗内): (%d, %d), 行高: %d" % (cx, cy, row_height))

    # 策略1：dump 里若有「明天」的 bounds，直接点「明天」那一行（明天在下一行，可能已露出）
    ok = False
    try:
        xml = d.dump_hierarchy()
        dump_path = os.path.join(_script_dir, "time_picker_dump.xml")
        with open(dump_path, "w", encoding="utf-8") as f:
            f.write(xml)
        print("  已保存 UI dump: %s" % dump_path)
        for m in re.finditer(r'text="明天"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml):
            tx = (int(m.group(1)) + int(m.group(3))) // 2
            ty = (int(m.group(2)) + int(m.group(4))) // 2
            print("  尝试直接点「明天」: (%d, %d)" % (tx, ty))
            d.click(tx, ty)
            time.sleep(0.5)
            ok = True
            break
        if not ok:
            for m in re.finditer(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"[^>]*text="明天"', xml):
                tx = (int(m.group(1)) + int(m.group(3))) // 2
                ty = (int(m.group(2)) + int(m.group(4))) // 2
                print("  尝试直接点「明天」(反序): (%d, %d)" % (tx, ty))
                d.click(tx, ty)
                time.sleep(0.5)
                ok = True
                break
    except Exception as e:
        print("  dump/点明天 异常: %s" % e)

    # 策略2：在 dayView 中心用拖拽（drag）向上移一行，滚轮对 drag 更敏感
    if not ok:
        row_height = 100
        print("  在日期列 (%d, %d) 用 u2.drag 向上拖 %dpx、0.6s，共 3 次…" % (cx, cy, row_height))
        for _ in range(3):
            d.drag(cx, cy, cx, cy - row_height, duration=0.6)
            time.sleep(0.5)
            if d(text="明天").exists(timeout=0.5) or d(textContains="明天").exists(timeout=0.5):
                ok = True
                break
    if not ok:
        print("  用 adb swipe 再试 3 次（500ms）…")
        for _ in range(3):
            adb("shell", "input", "swipe", str(cx), str(cy), str(cx), str(cy - 120), "500")
            time.sleep(0.5)
            if d(text="明天").exists(timeout=0.5) or d(textContains="明天").exists(timeout=0.5):
                ok = True
                break
    if not ok:
        print("  用 u2.swipe 再试 4 次（慢速 0.7s）…")
        for _ in range(4):
            d.swipe(cx, cy, cx, cy - 100, duration=0.7)
            time.sleep(0.5)
            if d(text="明天").exists(timeout=0.5) or d(textContains="明天").exists(timeout=0.5):
                ok = True
                break

    print("结果: %s" % ("已滚动到「明天」并停留" if ok else "已执行滑动，请查看手机日期列是否变为明天"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
