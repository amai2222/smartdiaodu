# -*- coding: utf-8 -*-
"""
哈啰车主页 · 按固定顺序操作（仅哈啰）：

  启动) 回到桌面 → 关闭哈啰 → 再打开哈啰（从干净状态开始）
  0) 若有「寻找乘客中」卡片，先点击进入 → 点右上角 3 个点 → 取消订单 → 再发布新行程
  1) 设置出发时间（点击出发时间行 → 弹窗选时间 → 确认）
  2) 设置出发地
  3) 设置目的地
  4) 点击「发布并搜索」
  5) 点击「寻找乘客中」进入订单列表

数据来源：环境变量或数据库（planned_trip_plans 第一条）。
用法：python probe/helo_setup_then_orders.py
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

# 哈啰包名，本机不同时可设环境变量 TANZI_HELO_PACKAGE
HELO_PKG = os.environ.get("TANZI_HELO_PACKAGE", "").strip() or "com.jingyao.easybike"
RES = HELO_PKG + ":id"


def get_departure_time():
    """出发时间：环境变量或数据库。返回如「明天 08:00」。"""
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


def get_origin_dest_from_db():
    """从数据库取第一条计划的 origin、destination。无则返回 (None, None)。"""
    try:
        from navigate_helo import get_planned_trip_from_db
        plan = get_planned_trip_from_db()
        o = (plan.get("origin") or "").strip() or None
        d = (plan.get("destination") or "").strip() or None
        return (o, d)
    except Exception:
        return (None, None)


try:
    import uiautomator2 as u2
    U2 = True
except ImportError:
    u2 = None
    U2 = False


def adb(*args):
    cmd = ["adb"] + (["-s", DEVICE] if DEVICE else []) + list(args)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=15)


def clean_start_then_launch_helo(d):
    """
    先回到桌面、关闭哈啰，再冷启动哈啰，保证从干净状态开始。
    流程：Home 键 → 强制停止哈啰 → 启动哈啰 → 等待到前台。
    """
    print("[启动] 回到桌面并关闭哈啰…")
    adb("shell", "input", "keyevent", "3")   # KEYCODE_HOME，回到桌面
    time.sleep(0.8)
    adb("shell", "am", "force-stop", HELO_PKG)
    time.sleep(0.5)
    print("[启动] 打开哈啰…")
    try:
        d.app_start(HELO_PKG, stop=True)
    except Exception as e:
        print("  u2.app_start 失败: %s，尝试 adb 启动…" % e)
        adb("shell", "am", "start", "-a", "android.intent.action.MAIN", "-c", "android.intent.category.LAUNCHER", "-p", HELO_PKG)
    for _ in range(28):
        time.sleep(1)
        pkg = (d.app_current() or {}).get("package", "")
        if pkg == HELO_PKG:
            print("  哈啰已打开并到前台。")
            time.sleep(3)
            return True
    return False


def ensure_helo_driver_page(d):
    """确保哈啰在前台且在车主页（有 clStartAddress / clStartTime）。若已在哈啰则只保证在车主页。"""
    pkg = (d.app_current() or {}).get("package", "")
    if pkg != HELO_PKG:
        # 未在哈啰，尝试启动（由调用方先执行 clean_start_then_launch_helo 时通常不会走到这里）
        print("[0] 启动哈啰…")
        try:
            d.app_start(HELO_PKG, stop=False)
        except Exception:
            pass
        try:
            if (d.app_current() or {}).get("package") != HELO_PKG:
                d.app_start(HELO_PKG, stop=True)
        except Exception as e:
            print("  u2.app_start 失败: %s" % e)
            adb("shell", "am", "start", "-a", "android.intent.action.MAIN", "-c", "android.intent.category.LAUNCHER", "-p", HELO_PKG)
        for _ in range(25):
            time.sleep(1)
            if (d.app_current() or {}).get("package") == HELO_PKG:
                time.sleep(3)
                break
        else:
            print("  请手动打开哈啰后重试。")
            return False
    # 若未已在车主页，尝试点「车主」底部 Tab，多试几次等页面加载
    for attempt in range(3):
        if d(resourceId=f"{RES}/clStartAddress").exists(timeout=3) or d(resourceId=f"{RES}/clStartTime").exists(timeout=2):
            break
        if d(text="车主").exists(timeout=2):
            d(text="车主").click()
            print("  已点击「车主」进入车主页。")
            time.sleep(3)
        elif d(textContains="车主").exists(timeout=2):
            d(textContains="车主").click()
            time.sleep(3)
        else:
            time.sleep(2)
    if not d(resourceId=f"{RES}/clStartAddress").exists(timeout=8):
        print("未找到车主页，请先手动打开哈啰并进入「车主」标签后再运行。")
        return False
    return True


def fill_two_boxes_and_click_first_result(d, city, detail, is_start=True):
    """填两个输入框并点第一个搜索结果。地址页加载需时，多等一会再找输入框。"""
    # 等地址搜索页出现（可能比时间弹窗关得晚）
    edit_city = d(className="android.widget.EditText", instance=0)
    if not edit_city.exists(timeout=6):
        # 若只有一个输入框，用「城市+详细」拼一起填
        single = d(className="android.widget.EditText")
        if single.exists(timeout=2):
            single.click()
            time.sleep(0.3)
            single.set_text("%s %s" % (city, detail))
            time.sleep(2)
            for btn in ("确定", "搜索", "完成", "确认"):
                if d(text=btn).exists(timeout=1):
                    d(text=btn).click()
                    break
            return True
        print("    未找到地址输入框，请确认已进入地址搜索页。")
        return False
    edit_city.click()
    time.sleep(0.3)
    edit_city.set_text(city)
    time.sleep(0.5)
    edit_detail = d(className="android.widget.EditText", instance=1)
    if edit_detail.exists(timeout=3):
        edit_detail.click()
        time.sleep(0.3)
        edit_detail.set_text(detail)
    else:
        # 只有一个输入框时把详细地址追加上去
        edit_city.set_text("%s %s" % (city, detail))
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


def try_cancel_existing_trip(d):
    """
    若当前有「寻找乘客中」卡片/按钮（已有在找乘客的行程），则：点击进入 → 点右上角 3 个点 → 取消订单。
    返回 True 表示已处理（取消或无需取消），可继续发布新行程。
    """
    # 在车主页查找「寻找乘客中」卡片或按钮，有则点击进入顺路订单页
    found_card = False
    for sel in [
        {"text": "寻找乘客中"},
        {"textContains": "寻找乘客中"},
    ]:
        try:
            el = d(**sel)
            if el.exists(timeout=2):
                el.click()
                print("  已点击「寻找乘客中」，进入顺路订单页。")
                time.sleep(2.5)
                found_card = True
                break
        except Exception:
            pass
    if not found_card:
        print("  未发现进行中行程，直接发布新行程。")
        return True

    # 在顺路订单页找右上角 3 个点（更多/菜单），多种选择器兜底
    dot_clicked = False
    for sel in [
        {"resourceId": f"{RES}/ivMore"},           # 常见命名
        {"resourceId": f"{RES}/tvMore"},
        {"description": "更多"},
        {"contentDescription": "更多"},
        {"text": "更多"},
        {"className": "android.widget.ImageView", "clickable": True},  # 可能为竖三点图标
    ]:
        try:
            el = d(**sel)
            if el.exists(timeout=2):
                el.click()
                print("  已点击右上角 3 个点（更多）。")
                dot_clicked = True
                time.sleep(1.2)
                break
        except Exception:
            pass
    if not dot_clicked:
        # 兜底：顺路订单页右侧区域常见为 (900, 200) 附近，按比例点击
        try:
            w, h = d.window_size()
            x, y = int(w * 0.92), int(h * 0.12)
            adb("shell", "input", "tap", str(x), str(y))
            print("  已通过坐标点击右上角区域（3 个点）。")
            time.sleep(1.2)
        except Exception:
            pass

    # 在弹出菜单中点击「取消订单」
    for sel in [
        {"text": "取消订单"},
        {"textContains": "取消订单"},
        {"description": "取消订单"},
    ]:
        try:
            el = d(**sel)
            if el.exists(timeout=2):
                el.click()
                print("  已点击「取消订单」。")
                time.sleep(1.5)
                break
        except Exception:
            pass

    # 若有二次确认弹窗，点「确定」或「确认」
    for btn in ("确定", "确认", "取消行程", "确认取消"):
        try:
            if d(text=btn).exists(timeout=1.5):
                d(text=btn).click()
                print("  已确认取消。")
                time.sleep(1.5)
                break
        except Exception:
            pass

    # 等待返回（可能回到车主页或列表）
    time.sleep(2)
    # 若在顺路订单页点了返回，可能需再点一次返回才到车主发布页；这里若仍不在车主页，后面 ensure 会再点「车主」
    return True


def click_finding_enter_orders(d):
    """点击「寻找乘客中」进入订单列表。"""
    time.sleep(2)
    for sel in [
        {"text": "寻找乘客中"},
        {"textContains": "寻找乘客中"},
        {"text": "寻找中"},
        {"textContains": "寻找中"},
        {"description": "寻找乘客中"},
        {"description": "寻找中"},
    ]:
        try:
            el = d(**sel)
            if el.exists(timeout=2):
                el.click()
                print("  已点击「寻找乘客中」，进入订单列表。")
                time.sleep(2)
                return True
        except Exception:
            pass
    # 发布后按钮变为「寻找乘客中」，用 resource-id 兜底
    if d(resourceId=f"{RES}/tvPublishButton").exists(timeout=1):
        t = (d(resourceId=f"{RES}/tvPublishButton").get_text() or "").strip()
        if "寻找" in t:
            d(resourceId=f"{RES}/tvPublishButton").click()
            print("  已点击发布按钮（当前文案：%s），进入订单列表。" % t)
            time.sleep(2)
            return True
    print("  未找到「寻找乘客中」控件，请手动点击进入订单列表。")
    return False


def main(origin=None, dest=None, departure_time=None):
    """
    顺序：1 出发时间 → 2 出发地 → 3 目的地 → 4 发布并搜索 → 5 寻找乘客中。
    origin/dest/departure_time 为 None 时用环境变量或数据库。
    """
    if not U2:
        print("请安装 uiautomator2: pip install uiautomator2")
        return 1

    _o, _d = get_origin_dest_from_db()
    origin = (origin or "").strip() or _o or START_ADDRESS
    dest = (dest or "").strip() or _d or END_ADDRESS
    depart_time = (departure_time or "").strip() or get_departure_time()

    print("=" * 50)
    print("  哈啰 · 顺序：出发时间 → 出发地 → 目的地 → 发布并搜索 → 寻找乘客中")
    print("=" * 50)
    print("  出发时间: %s" % depart_time)
    print("  出发地: %s" % origin)
    print("  目的地: %s" % dest)
    print("  设备: %s" % (DEVICE or "默认"))
    print()

    d = u2.connect(DEVICE) if DEVICE else u2.connect()
    # 先关闭手机当前 app、关闭哈啰，再打开哈啰，从干净状态开始
    if not clean_start_then_launch_helo(d):
        print("  哈啰未能启动到前台，请检查设备与安装。")
        return 1
    if not ensure_helo_driver_page(d):
        return 1

    # ---------- 0) 若有「寻找乘客中」则先取消当前行程，再发布新行程 ----------
    print("\n[0] 检查是否已有进行中行程（寻找乘客中）…")
    try_cancel_existing_trip(d)
    # 取消后可能不在车主发布页，确保回到车主页
    for _ in range(2):
        if d(resourceId=f"{RES}/clStartAddress").exists(timeout=3):
            break
        if d(text="车主").exists(timeout=1):
            d(text="车主").click()
            time.sleep(2)
        elif d(textContains="车主").exists(timeout=1):
            d(textContains="车主").click()
            time.sleep(2)
        else:
            adb("shell", "input", "keyevent", "4")  # BACK
            time.sleep(1.5)
    time.sleep(1)

    # ---------- 1) 先设置出发时间 ----------
    print("\n[1/4] 设置出发时间…")
    if d(resourceId=f"{RES}/clStartTime").exists(timeout=2):
        d(resourceId=f"{RES}/clStartTime").click()
        time.sleep(1.5)
        for _ in range(20):
            time.sleep(0.5)
            if d(text="请选择预计出发时间").exists(timeout=0.5) or d(textContains="预计出发时间").exists(timeout=0.5):
                break
        else:
            print("  未检测到时间选择弹窗。")
        time.sleep(1)
        confirmed = confirm_departure_time_dialog(d, target_time=depart_time)
        if not confirmed:
            # 若未识别到弹窗文案，仍尝试点一次「确认出发时间」关闭弹窗（resource-id 稳定）
            if d(resourceId=f"{RES}/tvConfirm").exists(timeout=1):
                d(resourceId=f"{RES}/tvConfirm").click()
                print("  [已通过 tvConfirm 点击「确认出发时间」]")
                time.sleep(0.6)
        # 必须等时间弹窗关闭后再操作，否则会挡住出发地/目的地页面
        for _ in range(20):
            time.sleep(0.4)
            if not d(text="请选择预计出发时间").exists(timeout=0.3) and not d(textContains="预计出发时间").exists(timeout=0.3):
                if d(resourceId=f"{RES}/clStartAddress").exists(timeout=0.5):
                    break
        time.sleep(1.2)
    else:
        print("  未找到出发时间行(clStartTime)。")
    time.sleep(1)

    # ---------- 2) 设置出发地 ----------
    print("\n[2/4] 设置出发地…")
    d(resourceId=f"{RES}/clStartAddress").click()
    time.sleep(4)
    city1, detail1 = split_city_and_detail(origin)
    if not city1 and not detail1:
        print("  出发地解析失败")
        return 1
    print("  城市=%s，详细=%s" % (city1, detail1))
    fill_two_boxes_and_click_first_result(d, city1, detail1, is_start=True)
    confirm_departure_time_dialog(d, target_time=depart_time)
    time.sleep(1.5)

    # ---------- 3) 设置目的地 ----------
    print("\n[3/4] 设置目的地…")
    end_el = d(resourceId=f"{RES}/clEndAddress")
    if not end_el.exists(timeout=3):
        if d(textContains="输入你的目的地").exists(timeout=1):
            d(textContains="输入你的目的地").click()
        else:
            adb("shell", "input", "tap", "540", "596")
    else:
        end_el.click()
    time.sleep(4)
    city2, detail2 = split_city_and_detail(dest)
    if not city2 and not detail2:
        print("  目的地解析失败")
        return 1
    print("  城市=%s，详细=%s" % (city2, detail2))
    fill_two_boxes_and_click_first_result(d, city2, detail2, is_start=False)
    confirm_departure_time_dialog(d, target_time=depart_time)
    time.sleep(1.5)

    # ---------- 4) 点击「发布并搜索」 ----------
    print("\n[4/4] 点击「发布并搜索」…")
    publish_clicked = False
    if d(resourceId=f"{RES}/tvPublishButton").exists(timeout=3):
        d(resourceId=f"{RES}/tvPublishButton").click()
        print("  已点击发布按钮(tvPublishButton)。")
        publish_clicked = True
    if not publish_clicked and d(text="发布并搜索").exists(timeout=2):
        d(text="发布并搜索").click()
        print("  已点击「发布并搜索」。")
        publish_clicked = True
    if not publish_clicked:
        adb("shell", "input", "tap", "540", "1028")
        print("  已通过坐标 (540,1028) 点击发布区域。")
    time.sleep(2)

    # ---------- 5) 点击「寻找乘客中」进入订单列表 ----------
    print("\n[5/5] 点击「寻找乘客中」进入订单列表…")
    click_finding_enter_orders(d)

    print("\n完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
