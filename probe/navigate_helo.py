# -*- coding: utf-8 -*-
"""
哈啰 App：通过 ADB 解析界面并模拟点击，自动进入「车主」顺风车大厅；
并将「你将从 XXX 出发」同步为数据库中的司机位置（driver_state.current_loc）。
默认用 adb；若安装 uiautomator2 则优先用其「按控件点击」，更接近手指点击、部分 App 才会响应。
司机位置从 Supabase 直接读取，不经大脑。
用法：先手动打开哈啰并保持在前台（已登录），再运行 python navigate_helo.py。
环境变量：TANZI_DEVICE、SUPABASE_URL、SUPABASE_SERVICE_ROLE_KEY、TANZI_DRIVER_ID；测试用 TANZI_DRIVER_LOC、TANZI_DRIVER_DEST（可选）。
"""

import os
import re
import subprocess
import sys
import time

# 从项目根目录加载 .env（便于读取 SUPABASE_SERVICE_ROLE_KEY）
try:
    from dotenv import load_dotenv
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(_root, ".env"))
except ImportError:
    pass

try:
    import requests
except ImportError:
    requests = None

try:
    import uiautomator2 as u2
    _U2_AVAILABLE = True
except ImportError:
    u2 = None
    _U2_AVAILABLE = False

# 设备序列号，空则默认第一台
DEVICE = os.environ.get("TANZI_DEVICE", "").strip()
# 司机 ID，用于从数据库读 current_loc（与 tanzi 一致）
DRIVER_ID = os.environ.get("TANZI_DRIVER_ID", "").strip() or "a0000001-0000-4000-8000-000000000001"
# Supabase：探子直接从数据库读司机位置，不经过大脑
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip() or "https://zqcctbcwibnqmumtqweu.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()

DUMP_PATH = "/sdcard/window_dump.xml"
LOCAL_DUMP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "window_dump.xml")

# 哈啰包名，用于检测前台与自动拉起
HELO_PACKAGE = "com.jingyao.easybike"

# 点击顺序：按顺序找这些文字并点击，进入车主大厅（可根据实际 App 文案调整）
CLICK_SEQUENCE = [
    "车主",       # 底部或顶部「车主」Tab
    "顺风车",     # 顺风车入口
    "大厅",       # 订单大厅（有的 App 叫「接单」「订单大厅」等）
]
# 若某一步找不到，可尝试的替代文案
ALTERNATIVES = {
    "车主": ["车主", "司机"],
    "顺风车": ["顺风车", "顺风"],
    "大厅": ["大厅", "订单大厅", "接单", "去接单"],
}
MAX_STEPS = 8
TAP_WAIT_SEC = 2.5


def adb_cmd(*args):
    cmd = ["adb"]
    if DEVICE:
        cmd.extend(["-s", DEVICE])
    cmd.extend(args)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=15)


def adb_tap_with_press(x: int, y: int, duration_ms: int = 80):
    """
    短按（swipe 同点 + 时长），部分 App 对瞬时 tap 无响应，用短按更可靠。
    """
    adb_cmd("shell", "input", "swipe", str(x), str(y), str(x), str(y), str(duration_ms))


def _supabase_headers():
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return None
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Accept": "application/json",
    }


# 缓存：同一次同步只查一次「第一条预期计划」，避免重复请求
_first_planned_trip_cache = None
_planned_trip_dict_cache = None


def get_first_planned_trip_from_db():
    """
    从 Supabase 读取与 web 端「预期计划」一致的数据：planned_trip_plans 表，
    按 completed.asc, sort_order.asc, departure_time.asc 取第一条，返回 (origin, destination)。
    与 GET /planned_trip 的 plans[0] 对应（第一条未完成计划即 web 上显示的第一条预期计划）。
    同一次运行内会缓存结果，避免出发地/目的地各查一次。
    """
    global _first_planned_trip_cache
    if _first_planned_trip_cache is not None:
        return _first_planned_trip_cache
    plan = get_planned_trip_from_db()
    if plan and (plan.get("origin") or plan.get("destination")):
        _first_planned_trip_cache = (
            (plan.get("origin") or "").strip() or None,
            (plan.get("destination") or "").strip() or None,
        )
    else:
        _first_planned_trip_cache = (None, None)
    return _first_planned_trip_cache


def get_planned_trip_from_db():
    """
    从 Supabase 读取第一条预期计划（planned_trip_plans），
    返回 {"origin", "destination", "departure_time"}，供探子整合脚本设置哈啰并抓单。
    """
    global _planned_trip_dict_cache
    if _planned_trip_dict_cache is not None:
        return _planned_trip_dict_cache
    if not requests:
        _planned_trip_dict_cache = {}
        return _planned_trip_dict_cache
    headers = _supabase_headers()
    if not headers:
        _planned_trip_dict_cache = {}
        return _planned_trip_dict_cache
    base = SUPABASE_URL.rstrip("/")
    try:
        url = f"{base}/rest/v1/planned_trip_plans"
        params = {
            "select": "origin,destination,departure_time",
            "order": "completed.asc,sort_order.asc,departure_time.asc",
            "limit": "1",
        }
        if DRIVER_ID:
            params["driver_id"] = f"eq.{DRIVER_ID.strip()}"
        r = requests.get(url, params=params, headers=headers, timeout=10)
        if r.status_code == 200 and isinstance(r.json(), list) and r.json():
            row = r.json()[0] or {}
            _planned_trip_dict_cache = {
                "origin": (row.get("origin") or "").strip() or None,
                "destination": (row.get("destination") or "").strip() or None,
                "departure_time": (row.get("departure_time") or "").strip() or None,
            }
            return _planned_trip_dict_cache
    except Exception:
        pass
    _planned_trip_dict_cache = {}
    return _planned_trip_dict_cache


def get_driver_loc_from_db():
    """
    出发地：与 web 端「预期计划」一致，优先用第一条预期计划的 origin（planned_trip_plans）；
    没有则用 driver_state.current_loc。
    """
    origin, _ = get_first_planned_trip_from_db()
    if origin:
        return origin
    if not DRIVER_ID or not requests:
        return None
    headers = _supabase_headers()
    if not headers:
        return None
    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/driver_state"
    params = {"driver_id": f"eq.{DRIVER_ID.strip()}", "select": "current_loc", "limit": "1"}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=10)
        if r.status_code != 200:
            return None
        data = r.json()
        if not isinstance(data, list) or not data:
            return None
        loc = (data[0] or {}).get("current_loc")
        return (loc or "").strip() or None
    except Exception:
        return None


def get_destination_from_db():
    """
    目的地：与 web 端「预期计划」一致，优先用第一条预期计划的 destination（planned_trip_plans）；
    没有则用 planned_trip_cycle_config.cycle_destination。
    """
    _, dest = get_first_planned_trip_from_db()
    if dest:
        return dest
    if not requests:
        return None
    headers = _supabase_headers()
    if not headers:
        return None
    base = SUPABASE_URL.rstrip("/")
    try:
        url = f"{base}/rest/v1/planned_trip_cycle_config"
        params = {"select": "cycle_destination", "limit": "1"}
        if DRIVER_ID:
            params["driver_id"] = f"eq.{DRIVER_ID.strip()}"
        r = requests.get(url, params=params, headers=headers, timeout=10)
        if r.status_code == 200 and isinstance(r.json(), list) and r.json():
            d = (r.json()[0] or {}).get("cycle_destination")
            if (d or "").strip():
                return (d or "").strip()
    except Exception:
        pass
    try:
        r = requests.get(f"{base}/rest/v1/planned_trip_cycle_config?select=cycle_destination&order=id.asc&limit=1", headers=headers, timeout=10)
        if r.status_code == 200 and isinstance(r.json(), list) and r.json():
            d = (r.json()[0] or {}).get("cycle_destination")
            if (d or "").strip():
                return (d or "").strip()
    except Exception:
        pass
    return None


def get_foreground_package() -> str:
    """获取当前前台应用包名。"""
    if _U2_AVAILABLE and u2:
        try:
            d = u2.connect(DEVICE) if DEVICE else u2.connect()
            cur = d.app_current()
            return (cur.get("package") or "").strip()
        except Exception:
            pass
    r = adb_cmd("shell", "dumpsys", "window", "windows")
    if r.returncode != 0:
        return ""
    out = (r.stdout or "") + (r.stderr or "")
    m = re.search(r"mCurrentFocus[^\n]*Window\{[^\s]+\s+(\S+)/", out)
    if m:
        return m.group(1).strip()
    return ""


def ensure_helo_foreground() -> bool:
    """
    若当前前台不是哈啰，则自动启动哈啰并等待加载。
    返回 True 表示哈啰已在前台（或已拉起）。
    """
    pkg = get_foreground_package()
    if pkg == HELO_PACKAGE:
        print("哈啰已在前台，无需拉起。")
        return True
    print("当前前台: %s，正在启动哈啰…" % (pkg or "未知"))
    # 使用 LAUNCHER 方式启动，避免指定具体 Activity 进入登录页
    adb_cmd("shell", "am", "start", "-a", "android.intent.action.MAIN", "-c", "android.intent.category.LAUNCHER", "-p", HELO_PACKAGE)
    time.sleep(6)
    pkg2 = get_foreground_package()
    if pkg2 == HELO_PACKAGE:
        print("哈啰已启动，等待界面稳定…")
        time.sleep(2)
        return True
    print("启动后前台仍为: %s，请确认哈啰已安装且可正常打开。" % (pkg2 or "未知"))
    return False


def dump_ui():
    adb_cmd("shell", "uiautomator", "dump", DUMP_PATH)
    r = adb_cmd("pull", DUMP_PATH, LOCAL_DUMP)
    if r.returncode != 0:
        print("拉取 dump 失败:", r.stderr or r.stdout)
        return None
    try:
        with open(LOCAL_DUMP, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception as e:
        print("读取 dump 失败:", e)
        return None


def parse_bounds_and_text(xml_content: str):
    """从 uiautomator dump 的 XML 里解析出所有带 text 或 content-desc 的节点及其 bounds。若子节点 text 有但 bounds 为 (0,0,0,0)，用最近的可点击父节点 bounds。"""
    nodes = []
    last_clickable_bounds = None
    for m in re.finditer(r'<node\s([^/]+?)(?:/>|>)', xml_content):
        blob = m.group(1)
        text_m = re.search(r'text="([^"]*)"', blob)
        desc_m = re.search(r'content-desc="([^"]*)"', blob)
        bounds_m = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', blob)
        click_m = re.search(r'clickable="(true|false)"', blob)
        text = (text_m.group(1) if text_m else "").strip() or (desc_m.group(1) if desc_m else "").strip()
        if not text:
            if bounds_m and click_m and click_m.group(1) == "true":
                x1, y1 = int(bounds_m.group(1)), int(bounds_m.group(2))
                x2, y2 = int(bounds_m.group(3)), int(bounds_m.group(4))
                if (x2 - x1) > 0 and (y2 - y1) > 0:
                    last_clickable_bounds = (x1, y1, x2, y2)
            continue
        if not bounds_m:
            continue
        x1, y1 = int(bounds_m.group(1)), int(bounds_m.group(2))
        x2, y2 = int(bounds_m.group(3)), int(bounds_m.group(4))
        clickable = click_m.group(1) == "true" if click_m else False
        if (x2 - x1) <= 0 or (y2 - y1) <= 0:
            if last_clickable_bounds:
                x1, y1, x2, y2 = last_clickable_bounds
            else:
                continue
        nodes.append({"text": text, "bounds": (x1, y1, x2, y2), "clickable": clickable})
    return nodes


def extract_order_texts(xml_content: str):
    """从 dump 中提取可能是订单的文案：含「元」的视为价格，时间段、起点/终点特征。"""
    nodes = parse_bounds_and_text(xml_content)
    skip = {"", "车主", "顺风车", "大厅", "登录", "获取验证码", "其他登录方式", "乘客", "我的", "首页", "逛逛", "钱包", "发布并搜索", "输入你的目的地", "你将从", "市内", "城际", "市内路线", "城际路线", "智能排序", "城市", "区/县", "筛选", "自动抢单", "愿摊高速费", "独享", "送货", "可协商", "免PK", "明天", "邀请有奖", "优惠加油", "个人中心", "接单攻略"}
    prices = []
    addresses = []
    times = []
    for n in nodes:
        t = (n["text"] or "").strip()
        if not t or t in skip or len(t) < 2:
            continue
        if "元" in t and re.search(r"[\d.]+", t):
            prices.append(t)
        elif re.search(r"今天|明天|\d{1,2}:\d{2}", t) and ("~" in t or ":" in t):
            times.append(t)
        elif len(t) >= 3 and re.search(r"[\u4e00-\u9fff]", t):
            if any(k in t for k in ("市", "区", "路", "县", "省", "镇", "乡", "村", "街", "号", "站", "中心", "苑", "场", "汇")):
                addresses.append(t)
    return {"prices": prices, "addresses": addresses, "times": times}


def find_and_tap(xml_content: str, target_text: str) -> bool:
    """在 dump 中查找包含 target_text 的节点并点击其中心；优先可点击节点，否则尝试同区域。"""
    nodes = parse_bounds_and_text(xml_content)
    # 先找可点击的
    for n in nodes:
        if not n["clickable"]:
            continue
        if target_text in n["text"] or n["text"] in target_text:
            x1, y1, x2, y2 = n["bounds"]
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            print("  点击 [%s] 坐标 (%d, %d)" % (n["text"][:20], cx, cy))
            r = adb_cmd("shell", "input", "tap", str(cx), str(cy))
            if r.returncode == 0:
                return True
            print("  tap 失败:", r.stderr)
            return False
    # 未找到可点击的，再试匹配文案的任意节点（父容器可能响应点击）
    for n in nodes:
        if target_text in n["text"] or n["text"] in target_text:
            x1, y1, x2, y2 = n["bounds"]
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            print("  点击(无 clickable) [%s] 坐标 (%d, %d)" % (n["text"][:20], cx, cy))
            r = adb_cmd("shell", "input", "tap", str(cx), str(cy))
            if r.returncode == 0:
                return True
    # 哈啰底部 Tab：文案在子节点 bounds 常为 0，用固定区域 fallback（约 1080 宽屏第二格=车主）
    if target_text == "车主" and "com.jingyao.easybike" in xml_content:
        cx, cy = 324, 2026
        print("  点击(fallback 车主 Tab) 坐标 (%d, %d)" % (cx, cy))
        r = adb_cmd("shell", "input", "tap", str(cx), str(cy))
        if r.returncode == 0:
            return True
    return False


def _u2_click_start_address() -> bool:
    """用 uiautomator2 按控件点击出发地（等同 View.performClick），部分 App 只响应此种点击。"""
    if not _U2_AVAILABLE or not u2:
        return False
    try:
        d = u2.connect(DEVICE) if DEVICE else u2.connect()
        for selector in [
            {"resourceId": "com.jingyao.easybike:id/clStartAddress"},
            {"resourceId": "com.jingyao.easybike:id/clStartAddress", "className": "android.view.ViewGroup"},
            {"textContains": "你将从", "clickable": True},
            {"textContains": "出发", "clickable": True},
        ]:
            el = d(**selector)
            if el.exists(timeout=1):
                el.click()
                print("  已用 uiautomator2 点击出发地控件")
                return True
        print("  uiautomator2 未找到出发地控件（请确认哈啰在前台且为车主页）")
    except Exception as e:
        print("  uiautomator2 点击失败:", e)
    return False


def _u2_click_end_address() -> bool:
    """用 uiautomator2 按控件点击目的地行（打开目的地地址栏）。"""
    if not _U2_AVAILABLE or not u2:
        return False
    try:
        d = u2.connect(DEVICE) if DEVICE else u2.connect()
        for selector in [
            {"resourceId": "com.jingyao.easybike:id/clEndAddress"},
            {"textContains": "输入你的目的地", "clickable": True},
            {"textContains": "目的地", "clickable": True},
        ]:
            el = d(**selector)
            if el.exists(timeout=1):
                el.click()
                print("  已用 uiautomator2 点击目的地控件")
                return True
        print("  uiautomator2 未找到目的地控件")
    except Exception as e:
        print("  uiautomator2 点击目的地失败:", e)
    return False


def tap_to_open_start_address_bar(xml_content: str) -> bool:
    """
    仅点击出发地区域，打开地址输入栏/地址页。不粘贴、不点确定。
    优先用 uiautomator2 按控件点击（与手指点击一致）；若无 u2 或失败则用 adb 短按坐标。
    """
    if not xml_content or "com.jingyao.easybike" not in xml_content:
        return False
    # 优先：u2 按控件点击（很多 App 只有这种才弹出）
    if _u2_click_start_address():
        return True
    nodes = parse_bounds_and_text(xml_content)

    def do_tap(cx: int, cy: int, label: str):
        print("  短按出发地 [%s] 打开地址栏，坐标 (%d, %d)" % (label, cx, cy))
        adb_tap_with_press(cx, cy, 80)

    # 1) 优先点右侧箭头（哈啰常用箭头打开地址选择）
    arrow = re.search(
        r'resource-id="[^"]*[Ss]tart[Aa]ddress[Aa]rrow[^"]*"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
        xml_content,
    )
    if not arrow:
        arrow = re.search(
            r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"[^>]*resource-id="[^"]*[Ss]tart[Aa]ddress[Aa]rrow',
            xml_content,
        )
    if arrow:
        x1, y1 = int(arrow.group(1)), int(arrow.group(2))
        x2, y2 = int(arrow.group(3)), int(arrow.group(4))
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        do_tap(cx, cy, "箭头")
        return True

    # 2) 整块出发地区域 clStartAddress（可点击的父布局）
    m = re.search(
        r'resource-id="[^"]*cl[Ss]tart[Aa]ddress[^"]*"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
        xml_content,
    )
    if not m:
        m = re.search(
            r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"[^>]*resource-id="[^"]*cl[Ss]tart[Aa]ddress',
            xml_content,
        )
    if m:
        x1, y1 = int(m.group(1)), int(m.group(2))
        x2, y2 = int(m.group(3)), int(m.group(4))
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        do_tap(cx, cy, "出发地区域")
        return True

    # 3) 按文案「你将从」「出发」点击（可能命中子 TextView 区域）
    for label in ("你将从", "出发"):
        for n in nodes:
            if label in (n["text"] or ""):
                x1, y1, x2, y2 = n["bounds"]
                cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                do_tap(cx, cy, label)
                return True

    # 4) 任意 resource-id 含 StartAddress 的控件
    m = re.search(
        r'resource-id="[^"]*[Ss]tart[Aa]ddress[^"]*"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
        xml_content,
    )
    if not m:
        m = re.search(
            r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"[^>]*resource-id="[^"]*[Ss]tart[Aa]ddress',
            xml_content,
        )
    if m:
        x1, y1 = int(m.group(1)), int(m.group(2))
        x2, y2 = int(m.group(3)), int(m.group(4))
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        do_tap(cx, cy, "StartAddress")
        return True

    # 5) 任意可点击且文案含「出发」的节点
    for n in nodes:
        if n["clickable"] and "出发" in (n["text"] or ""):
            x1, y1, x2, y2 = n["bounds"]
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            do_tap(cx, cy, (n["text"] or "")[:12])
            return True
    return False


def _fill_address_bar_and_confirm(address_text: str, label: str = "地址") -> bool:
    """
    在已打开的地址输入页上：优先用 u2 的 set_text 输入（中文更可靠），
    否则剪贴板 + 点击输入框 + 粘贴 + 点确定/搜索。
    """
    if not address_text or not address_text.strip():
        return False
    text = address_text.strip()
    time.sleep(1.0)

    # 1) 优先：uiautomator2 找 EditText 并 set_text
    if _U2_AVAILABLE and u2:
        try:
            d = u2.connect(DEVICE) if DEVICE else u2.connect()
            el = d(className="android.widget.EditText")
            if el.exists(timeout=3):
                el.click()
                time.sleep(0.5)
                el.set_text(text)
                print("  已用 u2 set_text 输入 %s: %s" % (label, text[:24] + ("…" if len(text) > 24 else "")))
                time.sleep(0.8)
                for btn in ("确定", "搜索", "完成", "确认"):
                    b = d(text=btn)
                    if b.exists(timeout=1):
                        b.click()
                        print("  已点击 [%s]" % btn)
                        return True
                return True
        except Exception as e:
            print("  u2 输入失败: %s，改用剪贴板" % e)

    # 2) 回退：剪贴板 + 点击输入框 + 粘贴
    adb_cmd("shell", "cmd", "clipboard", "set-text", text)
    time.sleep(0.3)
    xml2 = dump_ui()
    if not xml2:
        print("  打开地址栏后无法拉取界面。")
        return False
    for pattern, desc in [
        (r'class="android\.widget\.EditText"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', "EditText"),
        (r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"[^>]*class="android\.widget\.EditText"', "EditText"),
        (r'text="[^"]*[输搜][入索][^"]*"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', "输入/搜索"),
        (r'content-desc="[^"]*[输搜][入索][^"]*"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', "输入/搜索"),
    ]:
        m2 = re.search(pattern, xml2)
        if m2:
            x1, y1 = int(m2.group(1)), int(m2.group(2))
            x2, y2 = int(m2.group(3)), int(m2.group(4))
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            print("  点击输入框(%s)并粘贴 %s: %s" % (desc, label, text[:24] + ("…" if len(text) > 24 else "")))
            adb_cmd("shell", "input", "tap", str(cx), str(cy))
            time.sleep(0.6)
            adb_cmd("shell", "input", "keyevent", "279")
            time.sleep(0.8)
            adb_cmd("shell", "input", "keyevent", "279")
            time.sleep(0.5)
            for btn in ("确定", "搜索", "完成", "确认"):
                b = re.search(r'text="%s"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"' % re.escape(btn), xml2)
                if not b:
                    b = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"[^>]*text="%s"' % re.escape(btn), xml2)
                if b:
                    cx2, cy2 = (int(b.group(1)) + int(b.group(3))) // 2, (int(b.group(2)) + int(b.group(4))) // 2
                    print("  点击 [%s] 确认" % btn)
                    adb_cmd("shell", "input", "tap", str(cx2), str(cy2))
                    break
            return True
    print("  未检测到输入框，已发送粘贴键；若未生效请手动在地址栏粘贴。")
    adb_cmd("shell", "input", "keyevent", "279")
    time.sleep(0.8)
    adb_cmd("shell", "input", "keyevent", "279")
    return True


def set_helo_start_address_from_db(xml_content: str) -> bool:
    """
    将哈啰车主页「你将从 XXX 出发」设为数据库中的司机位置（driver_state.current_loc）。
    先点出发地打开地址栏，再粘贴并确认。无数据库时可用环境变量 TANZI_DRIVER_LOC。
    """
    driver_loc = get_driver_loc_from_db()
    if not driver_loc:
        driver_loc = os.environ.get("TANZI_DRIVER_LOC", "").strip()
    if not driver_loc:
        print("  未从数据库读到司机位置（请配置 SUPABASE_*、TANZI_DRIVER_ID，或设 TANZI_DRIVER_LOC 测试）。")
        return False
    if not tap_to_open_start_address_bar(xml_content):
        print("  未找到出发地控件，无法打开地址栏。")
        return False
    time.sleep(3.0)
    return _fill_address_bar_and_confirm(driver_loc, "出发地")


def set_helo_end_address_from_db(xml_content: str) -> bool:
    """
    将哈啰车主页「目的地」设为数据库中的目的地。
    数据来源：planned_trip_plans 第一条未完成计划的 destination，或 planned_trip_cycle_config.cycle_destination。
    无数据库时可用环境变量 TANZI_DRIVER_DEST。需 uiautomator2 点击目的地行才能弹出地址栏。
    """
    dest = get_destination_from_db()
    if not dest:
        dest = os.environ.get("TANZI_DRIVER_DEST", "").strip()
    if not dest:
        print("  未从数据库读到目的地（可配置 planned_trip_plans/planned_trip_cycle_config 或 TANZI_DRIVER_DEST）。")
        return False
    if not _u2_click_end_address():
        # 回退：从 dump 找 clEndAddress 坐标并 adb 短按
        m = re.search(
            r'resource-id="[^"]*cl[Ee]nd[Aa]ddress[^"]*"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
            xml_content,
        )
        if not m:
            m = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"[^>]*resource-id="[^"]*cl[Ee]nd[Aa]ddress', xml_content)
        if m:
            x1, y1 = int(m.group(1)), int(m.group(2))
            x2, y2 = int(m.group(3)), int(m.group(4))
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            print("  短按目的地区域，坐标 (%d, %d)" % (cx, cy))
            adb_tap_with_press(cx, cy, 80)
        else:
            print("  未找到目的地控件。")
            return False
    time.sleep(3.0)
    return _fill_address_bar_and_confirm(dest, "目的地")


def main():
    print("设备: %s" % (DEVICE or "默认"))
    # 若哈啰未打开则自动启动
    ensure_helo_foreground()
    print("")

    only_open = os.environ.get("TANZI_ONLY_OPEN_ADDRESS", "").strip().lower() in ("1", "true", "yes")
    if only_open:
        print("哈啰：仅点击出发地，打开地址栏（TANZI_ONLY_OPEN_ADDRESS=1）\n")
        # 优先直接用 u2 按控件点击（不依赖 dump，且更接近手指点击）
        if _U2_AVAILABLE and _u2_click_start_address():
            print("  已点击出发地，等待约 3 秒后地址栏应已打开。")
            time.sleep(3)
            return 0
        xml = dump_ui()
        if not xml:
            print("无法拉取界面，请检查 ADB 连接。")
            return 1
        if "com.jingyao.easybike" not in xml:
            print("当前可能不在哈啰界面，请先打开哈啰并进入车主页。")
            return 1
        ok = tap_to_open_start_address_bar(xml)
        if ok:
            print("  已点击出发地，等待约 3 秒后地址栏应已打开。")
            time.sleep(3)
        else:
            print("  未找到出发地控件。")
        return 0 if ok else 1

    print("哈啰：自动点击进入车主大厅并设置出发地/目的地")
    print("点击顺序: %s" % " -> ".join(CLICK_SEQUENCE))
    print("出发地/目的地：优先从数据库预期计划读取，测试时可设 TANZI_DRIVER_LOC、TANZI_DRIVER_DEST。\n")

    for step, label in enumerate(CLICK_SEQUENCE):
        if step >= MAX_STEPS:
            print("已达最大步数，停止")
            break
        print("\n[步骤 %d] 查找并点击: %s" % (step + 1, label))
        xml = dump_ui()
        if not xml:
            print("  无法获取界面 dump")
            time.sleep(TAP_WAIT_SEC)
            continue
        tried = [label] + ALTERNATIVES.get(label, [])
        tapped = False
        for t in tried:
            if find_and_tap(xml, t):
                tapped = True
                break
        if not tapped:
            print("  未找到可点击项: %s（可打开哈啰手动进入大厅后重新运行本脚本查看订单）" % tried)
        time.sleep(TAP_WAIT_SEC)
        # 进入车主页后先同步出发地、再同步目的地（数据库 → 哈啰）
        if step == 0 and "com.jingyao.easybike" in (xml or ""):
            time.sleep(1.5)
            xml2 = dump_ui()
            if xml2 and ("你将从" in xml2 or "出发" in xml2):
                print("\n[同步出发地] 从数据库读取司机位置并写入哈啰…")
                set_helo_start_address_from_db(xml2)
                time.sleep(2.0)
                # 同步目的地（需 u2 点击目的地行弹出地址栏）
                xml3 = dump_ui()
                if xml3 and ("输入你的目的地" in xml3 or "clEndAddress" in xml3):
                    print("\n[同步目的地] 从数据库读取目的地并写入哈啰…")
                    set_helo_end_address_from_db(xml3)
                time.sleep(1)

    print("\n请稍等界面加载…")
    time.sleep(2)
    xml = dump_ui()
    if not xml:
        print("无法拉取界面，请检查 ADB 连接。")
        return 1
    if "com.jingyao.easybike" not in xml:
        print("当前可能不在哈啰界面，请先打开哈啰并进入车主页后重试。")
        return 1
    # 若前面未成功同步，此处再试一次将出发地改为数据库司机位置
    if "你将从" in xml or "StartAddress" in xml or "出发" in xml:
        print("\n[同步出发地] 从数据库读取司机位置并写入哈啰…")
        set_helo_start_address_from_db(xml)
        time.sleep(1)
    # 解析并显示当前界面上的订单相关信息
    order_info = extract_order_texts(xml)
    print("\n" + "=" * 50)
    print("  当前界面 · 订单相关信息")
    print("=" * 50)
    if order_info["times"]:
        print("  出发时间：")
        for t in order_info["times"][:10]:
            print("    ", t)
    if order_info["addresses"]:
        print("  可能起点/终点：")
        for a in order_info["addresses"][:15]:
            print("    ", a)
    if order_info["prices"]:
        print("  可能价格：")
        for p in order_info["prices"][:10]:
            print("    ", p)
    if not (order_info["prices"] or order_info["addresses"] or order_info["times"]):
        print("  未识别到订单文案（可能尚未进入大厅，或大厅暂无订单；可手动滑到有订单再运行本脚本）。")
    print("=" * 50)
    return 0


if __name__ == "__main__":
    sys.exit(main())
