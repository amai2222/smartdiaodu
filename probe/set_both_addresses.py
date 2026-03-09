# -*- coding: utf-8 -*-
"""
串联设置哈啰出发地 + 目的地。每次选完地址后若弹出「请选择预计出发时间」则自动点确定。
用法：TANZI_DRIVER_LOC=... TANZI_DRIVER_DEST=...  python probe/set_both_addresses.py
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
from helo_address_helpers import split_city_and_detail, confirm_departure_time_dialog

DEVICE = os.environ.get("TANZI_DEVICE", "").strip()
DRIVER_ID = os.environ.get("TANZI_DRIVER_ID", "").strip() or "a0000001-0000-4000-8000-000000000001"
START_ADDRESS = os.environ.get("TANZI_DRIVER_LOC", "").strip() or "江苏省南通市如东县掘港街道荣生豪景花苑"
END_ADDRESS = os.environ.get("TANZI_DRIVER_DEST", "").strip() or "上海市浦江镇地铁站"


def get_departure_time_for_dialog():
    """从环境变量或数据库读取预计出发时间，供弹窗选择。返回如 "明天 08:00" 或 "08:00"。"""
    s = os.environ.get("TANZI_DRIVER_DEPART_TIME", "").strip()
    if s:
        return s
    try:
        import requests
        url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        if url and key:
            r = requests.get(
                f"{url}/rest/v1/planned_trip_plans",
                params={
                    "select": "departure_time",
                    "order": "completed.asc,sort_order.asc,departure_time.asc",
                    "limit": "1",
                    "driver_id": f"eq.{DRIVER_ID}",
                },
                headers={"apikey": key, "Authorization": f"Bearer {key}", "Accept": "application/json"},
                timeout=10,
            )
            if r.status_code == 200 and r.json():
                t = (r.json()[0] or {}).get("departure_time") or ""
                if isinstance(t, str) and t.strip():
                    return t.strip()
    except Exception:
        pass
    return "明天 08:00"

try:
    import uiautomator2 as u2
    U2 = True
except ImportError:
    u2 = None
    U2 = False


def adb(*args):
    cmd = ["adb"] + (["-s", DEVICE] if DEVICE else []) + list(args)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=15)


def fill_two_boxes_and_click_first_result(d, city, detail, is_start=True):
    """填两个输入框并点第一个搜索结果。is_start=True 用出发地关键词(荣生/豪景花苑)，False 用目的地(浦江镇/地铁站)。"""
    edit_city = d(className="android.widget.EditText", instance=0)
    edit_detail = d(className="android.widget.EditText", instance=1)
    if not edit_city.exists(timeout=3):
        return False
    edit_city.click()
    time.sleep(0.3)
    edit_city.set_text(city)
    time.sleep(0.5)
    if edit_detail.exists(timeout=2):
        edit_detail.click()
        time.sleep(0.3)
        edit_detail.set_text(detail)
    time.sleep(3)
    clicked = False
    if is_start:
        for exact in ("荣生·豪景花苑", "荣生·豪景花苑(西南门)", "荣生·豪景花苑(东北1门)"):
            if d(text=exact).exists(timeout=1):
                d(text=exact).click()
                print("    已点击第一个结果（%s）" % exact)
                clicked = True
                break
        if not clicked:
            for kw in ("荣生·豪景花苑", "荣生", "豪景花苑"):
                if kw in detail and d(className="android.widget.TextView", textContains=kw, instance=0).exists(timeout=2):
                    d(className="android.widget.TextView", textContains=kw, instance=0).click()
                    print("    已点击第一个结果（%s）" % kw)
                    clicked = True
                    break
        if not clicked:
            adb("shell", "uiautomator", "dump", "/sdcard/window_dump.xml")
            adb("pull", "/sdcard/window_dump.xml", os.path.join(_script_dir, "window_dump.xml"))
            dump_path = os.path.join(_script_dir, "window_dump.xml")
            if os.path.isfile(dump_path):
                with open(dump_path, "r", encoding="utf-8", errors="ignore") as f:
                    xml = f.read()
                for m in re.finditer(r'text="[^"]*荣生[^"]*"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml):
                    y1 = int(m.group(2))
                    if y1 > 800:
                        cx = (int(m.group(1)) + int(m.group(3))) // 2
                        cy = (y1 + int(m.group(4))) // 2
                        adb("shell", "input", "tap", str(cx), str(cy))
                        print("    已通过 bounds 点击第一个结果")
                        clicked = True
                        break
    else:
        for kw in ("浦江镇", "地铁站", "浦江镇地铁站"):
            if kw in detail:
                t = d(className="android.widget.TextView", textContains=kw, instance=0)
                if t.exists(timeout=2):
                    t.click()
                    print("    已点击第一个结果（%s）" % kw)
                    clicked = True
                    break
        if not clicked and len(detail) >= 2:
            if d(className="android.widget.TextView", textContains=detail[:2], instance=0).exists(timeout=2):
                d(className="android.widget.TextView", textContains=detail[:2], instance=0).click()
                clicked = True
    if not clicked:
        for btn in ("确定", "搜索", "完成", "确认"):
            if d(text=btn).exists(timeout=1):
                d(text=btn).click()
                break
    time.sleep(1)
    return True


def main(origin=None, dest=None, departure_time=None):
    """
    串联设置哈啰出发地、目的地、出发时间（弹窗），并点击发布并搜索。
    origin, dest, departure_time 为 None 时使用环境变量或数据库（get_departure_time_for_dialog）。
    供整合脚本传入数据库读取的计划。
    """
    start_addr = (origin or "").strip() or START_ADDRESS
    end_addr = (dest or "").strip() or END_ADDRESS
    depart_time = (departure_time or "").strip() or get_departure_time_for_dialog()

    print("=== 串联设置出发地 + 目的地 ===")
    print("出发地:", start_addr)
    print("目的地:", end_addr)
    print("出发时间:", depart_time)
    print("设备:", DEVICE or "默认")
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
                time.sleep(2)
                break
        else:
            print("  请手动打开哈啰到车主页后重试。")
            return 1

    if not d(resourceId="com.jingyao.easybike:id/clStartAddress").exists(timeout=3):
        if d(text="车主").exists(timeout=2):
            d(text="车主").click()
            print("  已点击「车主」进入车主页。")
            time.sleep(2)
        elif d(textContains="车主").exists(timeout=2):
            d(textContains="车主").click()
            time.sleep(2)
    if not d(resourceId="com.jingyao.easybike:id/clStartAddress").exists(timeout=5):
        print("未找到车主页出发地，请先打开哈啰并进入车主页。")
        return 1

    # ---------- 出发地 ----------
    print("\n[1/2] 设置出发地…")
    d(resourceId="com.jingyao.easybike:id/clStartAddress").click()
    time.sleep(4)
    city1, detail1 = split_city_and_detail(start_addr)
    if not city1 and not detail1:
        print("  出发地解析失败")
        return 1
    print("  城市=%s，详细地址=%s" % (city1, detail1))
    fill_two_boxes_and_click_first_result(d, city1, detail1, is_start=True)
    confirm_departure_time_dialog(d, target_time=depart_time)
    time.sleep(1.5)

    # ---------- 目的地 ----------
    print("\n[2/2] 设置目的地…")
    end_el = d(resourceId="com.jingyao.easybike:id/clEndAddress")
    if not end_el.exists(timeout=5):
        print("未找到目的地行，等待 2 秒后重试…")
        time.sleep(2)
        end_el = d(resourceId="com.jingyao.easybike:id/clEndAddress")
    if not end_el.exists(timeout=2):
        if d(textContains="输入你的目的地").exists(timeout=1):
            d(textContains="输入你的目的地").click()
            print("  已通过文案点击目的地行。")
        else:
            adb("shell", "input", "tap", "540", "596")
            print("  已通过坐标点击目的地行 (540,596)。")
    else:
        end_el.click()
    time.sleep(4)
    city2, detail2 = split_city_and_detail(end_addr)
    if not city2 and not detail2:
        print("  目的地解析失败")
        return 1
    print("  城市=%s，详细地址=%s" % (city2, detail2))
    fill_two_boxes_and_click_first_result(d, city2, detail2, is_start=False)
    confirm_departure_time_dialog(d, target_time=depart_time)

    # 点击「发布并搜索」
    time.sleep(1.5)
    print("\n[3/3] 点击「发布并搜索」…")
    publish_clicked = False
    try:
        if d(resourceId="com.jingyao.easybike:id/tvPublishButton").exists(timeout=3):
            d(resourceId="com.jingyao.easybike:id/tvPublishButton").click()
            print("  已点击发布按钮(tvPublishButton)。")
            publish_clicked = True
    except Exception:
        pass
    if not publish_clicked:
        try:
            pub = d(text="发布并搜索")
            if pub.exists(timeout=2):
                pub.click()
                print("  已点击「发布并搜索」。")
                publish_clicked = True
        except Exception:
            pass
    if not publish_clicked:
        adb("shell", "input", "tap", "540", "1028")
        print("  已通过坐标 (540,1028) 点击发布区域。")

    print("\n完成。出发地、目的地、出发时间已设置，已点击发布并搜索。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
