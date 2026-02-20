"""
顺风车智能调度系统 (Smart Dispatch Brain)
核心：带多点接送约束的车辆路径规划 (PDP - Pickup and Delivery Problem)
"""
import hashlib
import logging
import math
import os
import time
import traceback
from typing import List, Tuple, Optional, Any

# 优先从项目根目录 .env 加载环境变量（含 SUPABASE_SERVICE_ROLE_KEY 等）
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import bcrypt
import jwt
import requests
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp

# ================= 日志配置：500 排错必备 =================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    handlers=[
        logging.FileHandler("smartdiaodu_debug.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

app = FastAPI(title="私人顺风车智能调度大脑 (单机完全体)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================= 配置区 =================
BAIDU_AK = "xhDemVJisNK1JU962l0LKNGARjJvovdp"
BARK_KEY = "bGPZAHqjNjdiQZTg5GeWWG"
MAX_DETOUR_SECONDS = 900  # 绕路容忍阈值（秒），例如 15 分钟
REQUEST_TIMEOUT = 5       # 所有外部 API 统一超时（秒）
# 防骚扰：订单指纹 -> 上次处理时间戳
pushed_orders_cache: dict[str, float] = {}
# 业务模式：mode1=出发前找单 | mode2=路上接满 | mode3=送人后周边接单 | pause=停止
DRIVER_MODE = "mode2"
# 模式2：耽误时间范围(分钟)；高收益(元)以上可放宽到 detour_max
MODE2_DETOUR_MINUTES_MIN = 20
MODE2_DETOUR_MINUTES_MAX = 60
MODE2_HIGH_PROFIT_THRESHOLD = 100
# 模式3：基于「预估下一送客点」提前匹配，可串行重复（送完 A 接一单 B，送 B 时又可接 C，只要耽误在阈值内）
MODE3_MAX_MINUTES_TO_PICKUP = 30   # 预估送客点 → 新单起点 驾车不超过此分钟
MODE3_MAX_DETOUR_MINUTES = 25      # 剩余路线最多允许多绕的分钟数（耽误多久），每次接单都按此卡
# 模式1：出发前规划任务（内存，可后续迁到 Supabase）
planned_trip: dict[str, Any] = {}  # origin, destination, departure_time, min_orders, max_orders
# 推送后用户反馈：超时未操作则指纹该单不再推送；接单/停推由网页或链接回传
RESPONSE_TIMEOUT_SECONDS = 300   # 推送后若此秒数内未操作，视为放弃，指纹该单
RESPONSE_PAGE_BASE = ""          # 网页端「接单/是否继续接单」页面基础 URL，如 https://ui.xxx.com/response
abandoned_fingerprints: set[str] = set()   # 已放弃的订单指纹，不再推送
pending_response: dict[str, float] = {}   # fingerprint -> 推送时间戳，超时未响应则移入 abandoned
# 接单后通知探针取消已发布行程（探针轮询 probe_publish_trip 时会拿到 cancel_current_trip）
probe_cancel_trip_requested: bool = False
# 网页内推送：与 Bark 同时，写入 Supabase push_events 表，前端通过 Realtime 订阅展示
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip() or "https://zqcctbcwibnqmumtqweu.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip() or ""  # 服务端密钥，从 Dashboard → API 获取
# 登录：JWT 签发密钥（请改为随机字符串）；未配置时登录接口不可用
JWT_SECRET = os.environ.get("JWT_SECRET", "").strip() or "smartdiaodu_jwt_change_me"
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_SECONDS = 7 * 24 * 3600  # 7 天
# ==========================================


# ---------------------------------------------------------------------------
# 一、核心数据模型 (Data Models)
# ---------------------------------------------------------------------------

class CurrentState(BaseModel):
    """当前状态：司机位置 + 已接订单的起终点列表"""
    driver_loc: str
    pickups: List[str]
    deliveries: List[str]


class NewOrder(BaseModel):
    """新抓取的订单"""
    pickup: str
    delivery: str
    price: str


class EvaluateRequest(BaseModel):
    """评估接口请求体"""
    current_state: CurrentState
    new_order: NewOrder


class DriverModeUpdate(BaseModel):
    """调度模式切换请求体"""
    mode: str  # "mode1" | "mode2" | "mode3" | "pause"


class ModeConfigUpdate(BaseModel):
    """模式参数（可选字段，只更新传入的）"""
    mode2_detour_min: Optional[int] = None
    mode2_detour_max: Optional[int] = None
    mode2_high_profit_threshold: Optional[float] = None
    mode3_max_minutes_to_pickup: Optional[int] = None
    mode3_max_detour_minutes: Optional[int] = None   # 剩余路线最多多绕多少分钟


class PlannedTripUpdate(BaseModel):
    """模式1 规划任务"""
    origin: str
    destination: str
    departure_time: str   # 如 "06:00" 或 "2025-02-21 06:00"
    time_window_minutes: Optional[int] = 30   # 出发时间窗 ± 分钟
    min_orders: Optional[int] = 2
    max_orders: Optional[int] = 4


class GeocodeBatchRequest(BaseModel):
    """批量地理编码请求"""
    addresses: List[str]


class LoginRequest(BaseModel):
    """登录请求"""
    username: str
    password: str


# ---------------------------------------------------------------------------
# 登录：从 Supabase app_users 校验并签发 JWT
# ---------------------------------------------------------------------------
def _get_user_password_hash(username: str) -> Optional[str]:
    """从 Supabase app_users 表按用户名查 password_hash，无则返回 None。"""
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return None
    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/app_users"
    params = {"username": f"eq.{username}", "select": "password_hash"}
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Accept": "application/json",
    }
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            return None
        data = resp.json()
        if not data or not isinstance(data, list):
            return None
        return data[0].get("password_hash")
    except Exception as e:
        logger.warning("查询 app_users 失败: %s", e)
        return None


def _verify_password(plain: str, password_hash: Optional[str]) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False


def _create_token(username: str) -> str:
    payload = {"sub": username, "exp": int(time.time()) + JWT_EXPIRE_SECONDS}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _decode_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload.get("sub")
    except Exception:
        return None


security = HTTPBearer(auto_error=False)


@app.post("/login")
async def login(body: LoginRequest) -> dict:
    """
    用户名密码登录，校验 app_users 表后签发 JWT。
    需配置 SUPABASE_URL、SUPABASE_SERVICE_ROLE_KEY；默认账号 admin / 123456。
    """
    username = (body.username or "").strip()
    password = body.password or ""
    if not username:
        raise HTTPException(status_code=400, detail="用户名不能为空")
    hash_from_db = _get_user_password_hash(username)
    if not _verify_password(password, hash_from_db):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = _create_token(username)
    logger.info("用户 %s 登录成功", username)
    return {"token": token, "username": username}


@app.get("/auth/me")
async def auth_me(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> dict:
    """校验 JWT，返回当前用户名；未带有效 token 返回 401。"""
    if not credentials or not credentials.credentials:
        raise HTTPException(status_code=401, detail="未提供登录凭证")
    username = _decode_token(credentials.credentials)
    if not username:
        raise HTTPException(status_code=401, detail="登录已过期或无效")
    return {"username": username}


# ---------------------------------------------------------------------------
# 二、外部依赖 - 百度地图 (Geocoding + Duration Matrix)
# ---------------------------------------------------------------------------

def geocode_address(address: str) -> str:
    """
    单地址地理编码，返回 "lat,lng"。
    依赖：百度地图 Geocoding API。
    """
    url = "https://api.map.baidu.com/geocoding/v3/"
    params = {"address": address, "output": "json", "ak": BAIDU_AK}
    try:
        resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        logger.error("百度地理编码请求异常: %s", e)
        raise HTTPException(
            status_code=503,
            detail=f"地理编码服务不可用: {e!s}",
        ) from e

    if data.get("status") != 0:
        msg = data.get("message", "未知错误")
        logger.warning("地址解析失败 [%s]: %s", address, msg)
        raise HTTPException(
            status_code=400,
            detail=f"地址无法解析: {address}，原因: {msg}",
        )

    loc = data["result"]["location"]
    return f"{loc['lat']},{loc['lng']}"


def geocode_addresses(addresses: List[str]) -> List[str]:
    """批量地理编码，顺序与输入一致。任一失败即中止。"""
    coords: List[str] = []
    for addr in addresses:
        coords.append(geocode_address(addr))
    return coords


def get_duration_matrix(coords: List[str]) -> List[List[int]]:
    """
    获取所有点两两之间的驾车耗时（秒）。
    依赖：百度地图 Route Matrix API（驾车）。
    返回：matrix[i][j] = 从点 i 到点 j 的秒数。
    """
    points = "|".join(coords)
    url = "https://api.map.baidu.com/routematrix/v2/driving"
    params = {
        "origins": points,
        "destinations": points,
        "ak": BAIDU_AK,
        "tactics": 11,
    }
    try:
        resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        logger.error("百度路网矩阵请求异常: %s", e)
        raise HTTPException(
            status_code=503,
            detail=f"路网矩阵服务不可用: {e!s}",
        ) from e

    if data.get("status") != 0:
        msg = data.get("message", "未知错误")
        logger.warning("路网矩阵返回错误: %s", msg)
        raise HTTPException(
            status_code=502,
            detail=f"路网矩阵获取失败: {msg}",
        )

    n = len(coords)
    matrix: List[List[int]] = []
    for i in range(n):
        row: List[int] = []
        for j in range(n):
            idx = i * n + j
            row.append(data["result"][idx]["duration"]["value"])
        matrix.append(row)
    return matrix


def _bd09_to_wgs84(lat_bd: float, lng_bd: float) -> Tuple[float, float]:
    """百度 BD09 转 WGS84，供网页 Leaflet 显示。先 BD09->GCJ02 再 GCJ02->WGS84 近似。"""
    x_pi = math.pi * 3000.0 / 180.0
    x = lng_bd - 0.0065
    y = lat_bd - 0.006
    z = math.sqrt(x * x + y * y) - 0.00002 * math.sin(y * x_pi)
    theta = math.atan2(y, x) - 0.000003 * math.cos(x * x_pi)
    gcj_lng = z * math.cos(theta)
    gcj_lat = z * math.sin(theta)
    a, ee = 6378245.0, 0.00669342162296594323
    dlat = 300.0 + gcj_lng + 2.0 * gcj_lat + 0.1 * gcj_lat * gcj_lat + 0.1 * gcj_lat * gcj_lng + 0.1 * math.sqrt(abs(gcj_lat))
    dlat = 20.0 * math.sin(6.0 * gcj_lng * math.pi / 180.0) + 20.0 * math.sin(2.0 * gcj_lng * math.pi / 180.0) + dlat
    dlat = 20.0 * math.sin(gcj_lng * math.pi / 180.0) + 40.0 * math.sin(gcj_lng / 3.0 * math.pi / 180.0) + dlat
    dlat = 20.0 * math.sin(gcj_lng / 12.0 * math.pi / 180.0) * 2.0 / 3.0 + dlat
    dlat = dlat * 2.0 / 3.0 + 100.0
    dlng = 300.0 + gcj_lng + 2.0 * gcj_lat + 0.1 * gcj_lng * gcj_lng + 0.1 * gcj_lng * gcj_lat + 0.1 * math.sqrt(abs(gcj_lng))
    dlng = 20.0 * math.sin(6.0 * gcj_lng * math.pi / 180.0) + 20.0 * math.sin(gcj_lng * math.pi / 180.0) + dlng
    dlng = 20.0 * math.sin(gcj_lat * math.pi / 180.0) + 40.0 * math.sin(gcj_lat / 3.0 * math.pi / 180.0) + dlng
    dlng = 160.0 * math.sin(gcj_lat / 12.0 * math.pi / 180.0) + dlng
    dlng = dlng * 2.0 / 3.0 - 100.0
    wgs_lat = gcj_lat - (dlat * 180.0) / (a * (1.0 - ee) / (math.pow(1.0 - ee * math.sin(gcj_lat * math.pi / 180.0), 1.5)) * math.pi)
    wgs_lng = gcj_lng - (dlng * 180.0) / (a / math.sqrt(1.0 - ee * math.sin(gcj_lat * math.pi / 180.0) ** 2) * math.cos(gcj_lat * math.pi / 180.0) * math.pi)
    return (wgs_lat, wgs_lng)


def get_duration_between(origin_addr: str, dest_addr: str) -> int:
    """两点间驾车耗时（秒）。用于模式3：当前位→新单起点 是否在时效内。"""
    coords = geocode_addresses([origin_addr, dest_addr])
    matrix = get_duration_matrix(coords)
    return matrix[0][1]


# ---------------------------------------------------------------------------
# 三、核心算法 - OR-Tools PDP 路径规划
# ---------------------------------------------------------------------------

def solve_pdp_route(
    matrix: List[List[int]],
    num_pickup_delivery_pairs: int,
) -> Tuple[Optional[List[int]], int]:
    """
    带接送约束的车辆路径规划 (PDP)。
    约束：同一订单先接后送、同一车完成；司机回到起点的弧耗时为 0。
    返回：(最优路线节点索引列表, 总耗时秒数)；无解时 (None, 0)。
    """
    num_nodes = len(matrix)
    manager = pywrapcp.RoutingIndexManager(num_nodes, 1, 0)
    routing = pywrapcp.RoutingModel(manager)

    def duration_callback(from_index: int, to_index: int) -> int:
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        # 司机送到最后一站即结束，不计算返回起点的耗时
        if to_node == 0:
            return 0
        return matrix[from_node][to_node]

    transit_callback_index = routing.RegisterTransitCallback(duration_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)
    routing.AddDimension(transit_callback_index, 0, 300000, True, "Time")
    time_dimension = routing.GetDimensionOrDie("Time")

    for i in range(num_pickup_delivery_pairs):
        pickup_idx = manager.NodeToIndex(i + 1)
        delivery_idx = manager.NodeToIndex(i + 1 + num_pickup_delivery_pairs)
        routing.AddPickupAndDelivery(pickup_idx, delivery_idx)
        routing.solver().Add(
            routing.VehicleVar(pickup_idx) == routing.VehicleVar(delivery_idx)
        )
        routing.solver().Add(
            time_dimension.CumulVar(pickup_idx)
            <= time_dimension.CumulVar(delivery_idx)
        )

    search_params = pywrapcp.DefaultRoutingSearchParameters()
    search_params.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PARALLEL_CHEAPEST_INSERTION
    )
    solution = routing.SolveWithParameters(search_params)

    if not solution:
        return None, 0

    index = routing.Start(0)
    route_indices: List[int] = []
    total_time = 0
    while not routing.IsEnd(index):
        route_indices.append(manager.IndexToNode(index))
        prev_index = index
        index = solution.Value(routing.NextVar(index))
        total_time += routing.GetArcCostForVehicle(prev_index, index, 0)
    return route_indices, total_time


# ---------------------------------------------------------------------------
# 四、外部依赖 - Bark 推送 (极速强提醒，突破专注模式)
# ---------------------------------------------------------------------------

def push_to_bark(
    pickup: str,
    delivery: str,
    price: str,
    extra_mins: float,
    fingerprint: Optional[str] = None,
) -> None:
    """
    通过 Bark API 推送到 iPhone，level=timeSensitive 突破 iOS 专注模式。
    若传 fingerprint 且配置了 RESPONSE_PAGE_BASE，正文会带「接单/是否继续」操作链接。
    """
    if not BARK_KEY or BARK_KEY == "在这里填入你的Bark_Key":
        logger.info("未配置 BARK_KEY，跳过推送")
        return

    title = "🚨 发现极品顺路单！"
    body = f"接：{pickup}\n送：{delivery}\n价格：{price}元\n仅绕路：{extra_mins}分钟"
    if fingerprint and RESPONSE_PAGE_BASE:
        body += f"\n未在 {RESPONSE_TIMEOUT_SECONDS // 60} 分钟内操作将不再推送此单。接单/停推：{RESPONSE_PAGE_BASE.rstrip('/')}?fp={fingerprint}"
    elif fingerprint:
        body += f"\n未在规定时间内操作将不再推送此单；接单或停推请打开网页操作。"
    url = f"https://api.day.app/{BARK_KEY}/{title}/{body}"
    params = {
        "sound": "minuet",
        "level": "timeSensitive",
        "badge": "1",
        "isArchive": "1",
    }
    try:
        resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            logger.info("✅ 已推送到 iPhone: 绕路 %s 分钟, 赚 %s 元", extra_mins, price)
        else:
            logger.warning("❌ Bark 返回非 200: %s %s", resp.status_code, resp.text)
    except requests.RequestException as e:
        logger.error("❌ Bark 推送网络异常: %s", e)


def push_to_supabase_realtime(
    pickup: str,
    delivery: str,
    price: str,
    extra_mins: float,
    fingerprint: Optional[str] = None,
) -> None:
    """
    将推送事件写入 Supabase push_events 表，网页通过 Realtime 订阅即可在页内展示。
    与 Bark 同时调用；未配置 SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY 则跳过。
    """
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return
    response_url = None
    if fingerprint and RESPONSE_PAGE_BASE:
        response_url = f"{RESPONSE_PAGE_BASE.rstrip('/')}?fp={fingerprint}"
    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/push_events"
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    payload = {
        "fingerprint": fingerprint or "",
        "pickup": pickup,
        "delivery": delivery,
        "price": price,
        "extra_mins": round(extra_mins, 1),
        "response_url": response_url,
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=REQUEST_TIMEOUT)
        if resp.status_code in (200, 201):
            logger.info("✅ 已写入 push_events，网页 Realtime 可收到")
        else:
            logger.warning("❌ Supabase push_events 写入失败: %s %s", resp.status_code, resp.text[:200])
    except requests.RequestException as e:
        logger.error("❌ Supabase 写入异常: %s", e)


# ---------------------------------------------------------------------------
# 五、业务流水线：去重 → 地理编码 → 矩阵 → PDP(旧) → PDP(新) → 决策 → 推送
# ---------------------------------------------------------------------------

def _order_fingerprint(order: NewOrder) -> str:
    """新订单唯一指纹，用于防骚扰去重与放弃后不再推送。"""
    raw = f"{order.pickup}_{order.delivery}_{order.price}"
    return hashlib.md5(raw.encode()).hexdigest()


def _cleanup_pending_response() -> None:
    """将超时未操作的推送从 pending_response 移入 abandoned_fingerprints，后续不再推送该单。"""
    global abandoned_fingerprints, pending_response
    now = time.time()
    expired = [fp for fp, t in pending_response.items() if now - t >= RESPONSE_TIMEOUT_SECONDS]
    for fp in expired:
        abandoned_fingerprints.add(fp)
        del pending_response[fp]
        logger.info("订单指纹 %s 超时未操作，已放弃并不再推送", fp[:8])


# ---------------------------------------------------------------------------
# 调度模式与参数：GET / PUT（供网页、快捷指令调用）
# ---------------------------------------------------------------------------
VALID_MODES = ("mode1", "mode2", "mode3", "pause")

def _get_mode_config() -> dict:
    return {
        "mode2_detour_min": MODE2_DETOUR_MINUTES_MIN,
        "mode2_detour_max": MODE2_DETOUR_MINUTES_MAX,
        "mode2_high_profit_threshold": MODE2_HIGH_PROFIT_THRESHOLD,
        "mode3_max_minutes_to_pickup": MODE3_MAX_MINUTES_TO_PICKUP,
        "mode3_max_detour_minutes": MODE3_MAX_DETOUR_MINUTES,
        "response_timeout_seconds": RESPONSE_TIMEOUT_SECONDS,
        "response_page_base": RESPONSE_PAGE_BASE or None,
    }

@app.get("/driver_mode")
async def get_driver_mode() -> dict:
    """获取当前调度模式及模式参数。"""
    return {"mode": DRIVER_MODE, "config": _get_mode_config()}


@app.put("/driver_mode")
async def set_driver_mode(body: DriverModeUpdate) -> dict:
    """切换调度模式。mode1=出发前找单, mode2=路上接满, mode3=送人后周边, pause=停止。"""
    global DRIVER_MODE
    m = body.mode.strip().lower()
    if m not in VALID_MODES:
        raise HTTPException(status_code=400, detail=f"mode 必须是 {VALID_MODES} 之一")
    DRIVER_MODE = m
    logger.info("调度模式已切换为: %s", DRIVER_MODE)
    return {"mode": DRIVER_MODE}


@app.get("/driver_mode_config")
async def get_driver_mode_config() -> dict:
    """仅获取当前模式参数（用于前端展示/编辑）。"""
    return _get_mode_config()


@app.put("/driver_mode_config")
async def set_driver_mode_config(body: ModeConfigUpdate) -> dict:
    """更新模式参数（只更新传入的字段）。"""
    global MODE2_DETOUR_MINUTES_MIN, MODE2_DETOUR_MINUTES_MAX
    global MODE2_HIGH_PROFIT_THRESHOLD, MODE3_MAX_MINUTES_TO_PICKUP, MODE3_MAX_DETOUR_MINUTES
    if body.mode2_detour_min is not None:
        MODE2_DETOUR_MINUTES_MIN = max(0, body.mode2_detour_min)
    if body.mode2_detour_max is not None:
        MODE2_DETOUR_MINUTES_MAX = max(0, body.mode2_detour_max)
    if body.mode2_high_profit_threshold is not None:
        MODE2_HIGH_PROFIT_THRESHOLD = max(0, body.mode2_high_profit_threshold)
    if body.mode3_max_minutes_to_pickup is not None:
        MODE3_MAX_MINUTES_TO_PICKUP = max(1, body.mode3_max_minutes_to_pickup)
    if body.mode3_max_detour_minutes is not None:
        MODE3_MAX_DETOUR_MINUTES = max(0, body.mode3_max_detour_minutes)
    logger.info("模式参数已更新: %s", _get_mode_config())
    return _get_mode_config()


# ---------------------------------------------------------------------------
# 模式1：出发前规划任务（盯单条件，供探针/筛选使用；批量优化接口可后续扩展）
# ---------------------------------------------------------------------------
@app.get("/planned_trip")
async def get_planned_trip() -> dict:
    """获取当前设定的规划任务（模式1 找单条件）。无则返回空。"""
    return planned_trip if planned_trip else {"set": False}


@app.put("/planned_trip")
async def set_planned_trip(body: PlannedTripUpdate) -> dict:
    """设定规划任务：出发地、目的地、计划出发时间、2～4 单。探针/筛选可按此条件盯单。"""
    global planned_trip
    planned_trip = {
        "set": True,
        "origin": body.origin,
        "destination": body.destination,
        "departure_time": body.departure_time,
        "time_window_minutes": body.time_window_minutes or 30,
        "min_orders": body.min_orders or 2,
        "max_orders": body.max_orders or 4,
    }
    logger.info("规划任务已更新: %s -> %s, 出发 %s, %s～%s 单", body.origin, body.destination, body.departure_time, planned_trip["min_orders"], planned_trip["max_orders"])
    return planned_trip


@app.delete("/planned_trip")
async def clear_planned_trip() -> dict:
    """清除规划任务。"""
    global planned_trip
    planned_trip = {}
    return {"set": False}


# ---------------------------------------------------------------------------
# 网页地图：批量地理编码 + 当前路线预览（含经纬度，供地图绘制）
# ---------------------------------------------------------------------------
@app.post("/geocode_batch")
async def geocode_batch(body: GeocodeBatchRequest) -> list:
    """批量地理编码，返回 [{ address, lat, lng }, ...]（WGS84，供 Leaflet 等地图），失败项省略。"""
    out: List[dict] = []
    for addr in body.addresses:
        addr = (addr or "").strip()
        if not addr:
            continue
        try:
            coord_str = geocode_address(addr)
            lat_s, lng_s = coord_str.split(",", 1)
            lat_bd, lng_bd = float(lat_s), float(lng_s)
            wgs_lat, wgs_lng = _bd09_to_wgs84(lat_bd, lng_bd)
            out.append({"address": addr, "lat": wgs_lat, "lng": wgs_lng})
        except Exception as e:
            logger.warning("地理编码跳过 [%s]: %s", addr, e)
    return out


@app.post("/current_route_preview")
async def current_route_preview(req: dict) -> dict:
    """
    根据当前状态计算最优路线，返回途经点地址顺序及经纬度，供网页地图绘制。
    请求体：{ "current_state": { "driver_loc", "pickups", "deliveries" } }。
    """
    try:
        state = req.get("current_state") or {}
        driver_loc = (state.get("driver_loc") or "").strip()
        pickups = state.get("pickups") or []
        deliveries = state.get("deliveries") or []
        if isinstance(pickups, str):
            pickups = [s.strip() for s in pickups.split("\n") if s.strip()]
        if isinstance(deliveries, str):
            deliveries = [s.strip() for s in deliveries.split("\n") if s.strip()]
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"请求体格式错误: {e}") from e

    if not driver_loc:
        raise HTTPException(status_code=400, detail="driver_loc 不能为空")
    if len(pickups) != len(deliveries):
        raise HTTPException(status_code=400, detail="pickups 与 deliveries 数量须一致")

    if not pickups:
        try:
            coord_str = geocode_address(driver_loc)
            lat_s, lng_s = coord_str.split(",", 1)
            lat_bd, lng_bd = float(lat_s), float(lng_s)
            wgs_lat, wgs_lng = _bd09_to_wgs84(lat_bd, lng_bd)
            return {
                "route_addresses": [driver_loc],
                "route_coords": [[wgs_lat, wgs_lng]],
                "point_types": ["driver"],
                "total_time_seconds": 0,
            }
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"地理编码失败: {e}") from e

    addresses = [driver_loc] + list(pickups) + list(deliveries)
    coords = geocode_addresses(addresses)
    matrix = get_duration_matrix(coords)
    route_indices, total_time = solve_pdp_route(matrix, len(pickups))
    if not route_indices:
        raise HTTPException(status_code=422, detail="无法规划出符合逻辑的路线")

    n_pairs = len(pickups)
    route_addresses = [addresses[i] for i in route_indices]
    point_types = []
    for i in route_indices:
        if i == 0:
            point_types.append("driver")
        elif 1 <= i <= n_pairs:
            point_types.append("pickup")
        else:
            point_types.append("delivery")
    route_coords = []
    for i in route_indices:
        parts = coords[i].split(",", 1)
        lat_bd, lng_bd = float(parts[0]), float(parts[1])
        wgs_lat, wgs_lng = _bd09_to_wgs84(lat_bd, lng_bd)
        route_coords.append([wgs_lat, wgs_lng])
    return {
        "route_addresses": route_addresses,
        "route_coords": route_coords,
        "point_types": point_types,
        "total_time_seconds": total_time,
    }


@app.post("/probe_publish_trip")
async def probe_publish_trip(req: dict) -> dict:
    """
    探针用：根据当前状态算出「建议在平台发布的行程」，供探针号在 App 里自动填表发布。
    平台（哈啰/滴滴）可能要求先发布行程才展示该路线的顺路单；探针可轮询此接口并自动填 起点/终点/出发时间 后点发布。
    返回：origin（建议起点）, destination（建议终点）, depart_time（建议出发时间，可选）。
    """
    try:
        state = req.get("current_state") or {}
        driver_loc = (state.get("driver_loc") or "").strip()
        pickups = state.get("pickups") or []
        deliveries = state.get("deliveries") or []
        if isinstance(pickups, str):
            pickups = [s.strip() for s in pickups.split("\n") if s.strip()]
        if isinstance(deliveries, str):
            deliveries = [s.strip() for s in deliveries.split("\n") if s.strip()]
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"请求体格式错误: {e}") from e

    if not driver_loc:
        raise HTTPException(status_code=400, detail="driver_loc 不能为空")
    if len(pickups) != len(deliveries):
        raise HTTPException(status_code=400, detail="pickups 与 deliveries 数量须一致")

    global probe_cancel_trip_requested
    cancel_now = probe_cancel_trip_requested
    if cancel_now:
        probe_cancel_trip_requested = False
        logger.info("探针本次请求携带「取消已发布行程」信号")

    def _resp(origin: str, dest: str, depart: str, hint: str) -> dict:
        out = {"origin": origin, "destination": dest, "depart_time": depart, "hint": hint}
        if cancel_now:
            out["cancel_current_trip"] = True
        return out

    if not pickups:
        return _resp(driver_loc, driver_loc, "", "当前无已接单，起点=终点=司机位置；探针可暂不发布或按需填写")

    addresses = [driver_loc] + list(pickups) + list(deliveries)
    coords = geocode_addresses(addresses)
    matrix = get_duration_matrix(coords)
    route_indices, _ = solve_pdp_route(matrix, len(pickups))
    if not route_indices:
        raise HTTPException(status_code=422, detail="无法规划出路线")

    n_pairs = len(pickups)
    route_addresses = [addresses[i] for i in route_indices]
    point_types = []
    for i in route_indices:
        if i == 0:
            point_types.append("driver")
        elif 1 <= i <= n_pairs:
            point_types.append("pickup")
        else:
            point_types.append("delivery")

    first_delivery_addr = None
    for i, idx in enumerate(route_indices):
        if point_types[i] == "delivery":
            first_delivery_addr = route_addresses[i]
            break
    last_addr = route_addresses[-1]
    origin = first_delivery_addr if first_delivery_addr else route_addresses[1]
    destination = last_addr
    depart_time = time.strftime("%H:%M", time.localtime())

    return _resp(origin, destination, depart_time, "从第一个客人下车点至最后一站，探针可据此在 App 内自动填写并发布行程")


# ---------------------------------------------------------------------------
# 推送后用户反馈：接单/放弃 + 是否继续用模式2推送（供网页或 Bark 内链接调用）
# ---------------------------------------------------------------------------
@app.get("/order_response")
async def order_response(
    fingerprint: str,
    accepted: str,   # "1" / "0" 或 "true" / "false"
    continue_accepting: str,  # "1" / "0" 或 "true" / "false"
) -> dict:
    """
    用户在网页或链接上点击「接单/不接」与「是否继续接单」后调用。
    accepted=1 表示接单，=0 表示放弃该单（指纹，不再推送）；
    continue_accepting=1 表示继续用模式2推送，=0 表示暂停推送（切到 pause）。
    """
    global DRIVER_MODE, abandoned_fingerprints, pending_response, probe_cancel_trip_requested
    fp = (fingerprint or "").strip()
    if not fp:
        raise HTTPException(status_code=400, detail="缺少 fingerprint 参数")
    ac = accepted.strip().lower() in ("1", "true", "yes")
    cont = continue_accepting.strip().lower() in ("1", "true", "yes")

    if fp in pending_response:
        del pending_response[fp]
    if not ac:
        abandoned_fingerprints.add(fp)
        logger.info("用户放弃订单（指纹 %s），已加入放弃列表不再推送", fp[:8])
    if ac:
        probe_cancel_trip_requested = True
        logger.info("用户已接单，已通知探针取消对应已发布行程")
    if not cont:
        DRIVER_MODE = "pause"
        logger.info("用户选择不再接单，已切换为 pause")

    if ac and cont:
        return {"ok": True, "message": "已记录接单，将继续为你推送顺路单（模式2）"}
    if ac and not cont:
        return {"ok": True, "message": "已记录接单，已暂停推送；需要时请手动切回模式2"}
    if not ac and cont:
        return {"ok": True, "message": "已放弃该单并不再推送此单，将继续推送其他顺路单"}
    return {"ok": True, "message": "已放弃该单并暂停推送；需要时请手动切回模式2"}


@app.post("/evaluate_new_order")
async def evaluate_new_order(req: EvaluateRequest) -> dict:
    """
    评估新订单是否值得接：绕路时间 <= 阈值则视为顺路单并推送 Bark。
    """
    current = req.current_state
    new_order = req.new_order

    # ---------- 0. 调度模式 ----------
    if DRIVER_MODE == "pause":
        logger.info("当前为停止接单模式，跳过评估")
        return {"status": "ignored", "reason": "当前为停止接单模式，不评估新单"}
    if DRIVER_MODE == "mode1":
        logger.info("模式1为出发前规划，单笔评估不适用")
        return {"status": "ignored", "reason": "模式1为出发前找单，请使用规划任务接口筛选并批量优化 2～4 单"}

    # ---------- 1. 防骚扰与去重 ----------
    fingerprint = _order_fingerprint(new_order)
    now = time.time()
    _cleanup_pending_response()
    if fingerprint in abandoned_fingerprints:
        logger.info("订单已放弃过（指纹），不再推送")
        return {"status": "ignored", "reason": "该订单已放弃或超时未操作，不再推送"}
    if fingerprint in pushed_orders_cache:
        last = pushed_orders_cache[fingerprint]
        if now - last < 30 * 60:
            logger.info("防骚扰拦截: 订单 30 分钟内已处理过")
            return {"status": "ignored", "reason": "该订单最近已评估/推送过，防骚扰拦截生效"}

    try:
        logger.info(
            "评估新订单: %s -> %s (￥%s)",
            new_order.pickup,
            new_order.delivery,
            new_order.price,
        )

        # ---------- 模式3 专用：预估下一送客点 → 周边时效 + 剩余路线耽误（可串行：每次送客前都按此规则找单） ----------
        if DRIVER_MODE == "mode3" and len(current.deliveries) >= 1:
            # 根据当前位到各送客点耗时，预估「即将放下客人」的地点（取最近的一个）
            addr_eta = [current.driver_loc] + current.deliveries
            coords_eta = geocode_addresses(addr_eta)
            matrix_eta = get_duration_matrix(coords_eta)
            j = min(range(len(current.deliveries)), key=lambda i: matrix_eta[0][i + 1])
            drop_location = current.deliveries[j]
            eta_seconds = matrix_eta[0][j + 1]
            eta_minutes = round(eta_seconds / 60, 1)
            remaining_pickups = [p for i, p in enumerate(current.pickups) if i != j]
            remaining_deliveries = [d for i, d in enumerate(current.deliveries) if i != j]

            # 新单起点须在「预估送客点」周边时效内（不是当前位）
            to_pickup_seconds = get_duration_between(drop_location, new_order.pickup)
            to_pickup_minutes = to_pickup_seconds / 60
            if to_pickup_minutes > MODE3_MAX_MINUTES_TO_PICKUP:
                return {
                    "status": "rejected",
                    "reason": f"新单起点距预估送客点约 {round(to_pickup_minutes, 1)} 分钟，超过设定时效 {MODE3_MAX_MINUTES_TO_PICKUP} 分钟",
                }

            # 剩余路线：不接 vs 接该单，看耽误是否在「不能耽误太久」内
            old_addr = [drop_location] + remaining_pickups + remaining_deliveries
            new_addr = [drop_location] + remaining_pickups + [new_order.pickup] + remaining_deliveries + [new_order.delivery]
            old_coords = geocode_addresses(old_addr)
            new_coords = geocode_addresses(new_addr)
            old_matrix = get_duration_matrix(old_coords)
            new_matrix = get_duration_matrix(new_coords)
            _, old_total = solve_pdp_route(old_matrix, len(remaining_pickups))
            new_route_idx, new_total = solve_pdp_route(new_matrix, len(remaining_pickups) + 1)
            if not new_route_idx:
                return {"status": "rejected", "reason": "接入该单后剩余路线无法规划出合理顺序"}
            extra_seconds = new_total - old_total
            extra_minutes = round(extra_seconds / 60, 1)
            if extra_seconds > MODE3_MAX_DETOUR_MINUTES * 60:
                return {
                    "status": "rejected",
                    "reason": f"接该单会使剩余路线多绕约 {extra_minutes} 分钟，超过允许 {MODE3_MAX_DETOUR_MINUTES} 分钟（不能耽误太久）",
                }

            pushed_orders_cache[fingerprint] = now
            pending_response[fingerprint] = now
            push_to_bark(new_order.pickup, new_order.delivery, new_order.price, extra_minutes, fingerprint)
            push_to_supabase_realtime(new_order.pickup, new_order.delivery, new_order.price, extra_minutes, fingerprint)
            route_preview = [new_addr[i] for i in new_route_idx]
            return {
                "status": "matched",
                "message": f"预计约 {eta_minutes} 分钟后在「{drop_location}」送完当前客人；该单起点距该处约 {round(to_pickup_minutes, 1)} 分钟，剩余路线仅多 {extra_minutes} 分钟，已推送",
                "detour_minutes": extra_minutes,
                "profit": new_order.price,
                "new_route_preview": route_preview,
                "eta_minutes_to_next_drop": eta_minutes,
                "next_drop_address": drop_location,
            }

        # ---------- 2. 地理编码（当前行程 + 新单） ----------
        old_addresses = [current.driver_loc] + current.pickups + current.deliveries
        old_coords = geocode_addresses(old_addresses)

        new_pickups = current.pickups + [new_order.pickup]
        new_deliveries = current.deliveries + [new_order.delivery]
        new_addresses = [current.driver_loc] + new_pickups + new_deliveries
        new_coords = geocode_addresses(new_addresses)

        # ---------- 3. 耗时矩阵 ----------
        old_matrix = get_duration_matrix(old_coords)
        new_matrix = get_duration_matrix(new_coords)

        # ---------- 4. 运筹学路径规划：不接新单 vs 接新单 ----------
        _, old_total_time = solve_pdp_route(old_matrix, len(current.pickups))
        new_route_indices, new_total_time = solve_pdp_route(
            new_matrix, len(new_pickups)
        )

        if not new_route_indices:
            logger.warning("PDP 无解: 无法规划出符合逻辑的合并路线")
            return {"status": "rejected", "reason": "无法规划出符合逻辑的合并路线"}

        # ---------- 5. 商业决策：绕路/时效判定（模式2 或 模式3 无待送客时） ----------
        extra_time_seconds = new_total_time - old_total_time
        extra_time_minutes = round(extra_time_seconds / 60, 1)

        # 模式3 且当前没有待送客：按「当前位→新单起点」时效卡
        if DRIVER_MODE == "mode3" and len(current.deliveries) == 0:
            to_pickup_seconds = get_duration_between(current.driver_loc, new_order.pickup)
            if to_pickup_seconds > MODE3_MAX_MINUTES_TO_PICKUP * 60:
                return {
                    "status": "rejected",
                    "reason": f"新单起点距当前位置约 {round(to_pickup_seconds/60, 1)} 分钟，超过设定时效 {MODE3_MAX_MINUTES_TO_PICKUP} 分钟",
                }

        # 模式2：规定耽误时间内可接；超过 detour_min 只在高收益时放宽到 detour_max
        if DRIVER_MODE == "mode2":
            detour_max_seconds = MODE2_DETOUR_MINUTES_MAX * 60
            detour_min_seconds = MODE2_DETOUR_MINUTES_MIN * 60
            if extra_time_seconds > detour_max_seconds:
                return {
                    "status": "rejected",
                    "reason": f"绕路将增加 {extra_time_minutes} 分钟，超过最大允许 {MODE2_DETOUR_MINUTES_MAX} 分钟",
                }
            if extra_time_seconds > detour_min_seconds:
                try:
                    price_val = float(new_order.price)
                except (TypeError, ValueError):
                    price_val = 0
                if price_val < MODE2_HIGH_PROFIT_THRESHOLD:
                    return {
                        "status": "rejected",
                        "reason": f"绕路 {extra_time_minutes} 分钟超过轻松接单范围（{MODE2_DETOUR_MINUTES_MIN} 分钟），且收益未达高收益门槛（{MODE2_HIGH_PROFIT_THRESHOLD} 元）",
                    }
        # 其他模式兜底：按固定 15 分钟绕路阈值
        if DRIVER_MODE not in ("mode2", "mode3") and extra_time_seconds > MAX_DETOUR_SECONDS:
            return {
                "status": "rejected",
                "reason": f"绕路太远，将增加 {extra_time_minutes} 分钟，已放弃该单",
            }

        # ---------- 6. 接单：写缓存 + 待响应 + Bark 推送 ----------
        pushed_orders_cache[fingerprint] = now
        pending_response[fingerprint] = now
        push_to_bark(
            new_order.pickup,
            new_order.delivery,
            new_order.price,
            extra_time_minutes,
            fingerprint,
        )
        push_to_supabase_realtime(
            new_order.pickup,
            new_order.delivery,
            new_order.price,
            extra_time_minutes,
            fingerprint,
        )
        route_preview = [new_addresses[i] for i in new_route_indices]

        return {
            "status": "matched",
            "message": "极度顺路，已触发手机推送",
            "detour_minutes": extra_time_minutes,
            "profit": new_order.price,
            "new_route_preview": route_preview,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("订单评估过程发生未捕获异常: %s", e)
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"服务器内部运算异常，详见控制台与 smartdiaodu_debug.log: {e!s}",
        ) from e


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("smartdiaodu:app", host="0.0.0.0", port=8000, reload=True)
