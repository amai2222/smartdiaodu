# -*- coding: utf-8 -*-
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
from typing import Any, Dict, List, Optional, Set, Tuple

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
# 以下为默认值，启动时由 _load_app_config_from_db() 从 app_config 表覆盖（除 Supabase/JWT 外仅从 DB 读）
BAIDU_AK = "wxw2PvK3nWeOCGk1rZDe2krnlc1jbzsc"
BAIDU_SERVICE_ID = "119231078"
BARK_KEY = "bGPZAHqjNjdiQZTg5GeWWG"
MAX_DETOUR_SECONDS = 900
REQUEST_TIMEOUT = 5
pushed_orders_cache: Dict[str, float] = {}
DRIVER_MODE = "mode2"
MODE2_DETOUR_MINUTES_MIN = 20
MODE2_DETOUR_MINUTES_MAX = 60
MODE2_HIGH_PROFIT_THRESHOLD = 100
MODE3_MAX_MINUTES_TO_PICKUP = 30
MODE3_MAX_DETOUR_MINUTES = 25
planned_trips: List[Dict[str, Any]] = []
RESPONSE_TIMEOUT_SECONDS = 300
RESPONSE_PAGE_BASE = ""
abandoned_fingerprints: Set[str] = set()
pending_response: Dict[str, float] = {}
probe_cancel_trip_requested: bool = False

# 仅从环境变量读取：连接数据库与登录签发
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip() or "https://zqcctbcwibnqmumtqweu.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip() or ""
JWT_SECRET = os.environ.get("JWT_SECRET", "").strip() or "smartdiaodu_jwt_change_me"
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_SECONDS = 7 * 24 * 3600


def _load_app_config_from_db() -> None:
    """从 app_config 表加载配置并覆盖全局变量（除 Supabase/JWT 外）。"""
    global BAIDU_AK, BAIDU_SERVICE_ID, BARK_KEY, MAX_DETOUR_SECONDS, REQUEST_TIMEOUT
    global DRIVER_MODE, MODE2_DETOUR_MINUTES_MIN, MODE2_DETOUR_MINUTES_MAX, MODE2_HIGH_PROFIT_THRESHOLD
    global MODE3_MAX_MINUTES_TO_PICKUP, MODE3_MAX_DETOUR_MINUTES
    global RESPONSE_TIMEOUT_SECONDS, RESPONSE_PAGE_BASE
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        logger.warning("未配置 SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY，跳过从 DB 加载 app_config")
        return
    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/app_config?select=key,value"
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            logger.warning("app_config 请求失败 status=%s", resp.status_code)
            return
        data = resp.json()
        if not isinstance(data, list):
            return
        cfg = {row["key"]: (row.get("value") or "").strip() for row in data if isinstance(row, dict) and "key" in row}
        if cfg.get("baidu_ak_server"):
            BAIDU_AK = cfg["baidu_ak_server"]
        elif cfg.get("baidu_map_ak"):
            BAIDU_AK = cfg["baidu_map_ak"]
        if cfg.get("baidu_service_id"):
            BAIDU_SERVICE_ID = cfg["baidu_service_id"]
        if "bark_key" in cfg:
            BARK_KEY = cfg["bark_key"]
        if cfg.get("max_detour_seconds"):
            try:
                MAX_DETOUR_SECONDS = int(cfg["max_detour_seconds"])
            except ValueError:
                pass
        if cfg.get("request_timeout"):
            try:
                REQUEST_TIMEOUT = int(cfg["request_timeout"])
            except ValueError:
                pass
        if cfg.get("driver_mode") in ("mode1", "mode2", "mode3", "pause"):
            DRIVER_MODE = cfg["driver_mode"]
        if cfg.get("mode2_detour_min"):
            try:
                MODE2_DETOUR_MINUTES_MIN = max(0, int(cfg["mode2_detour_min"]))
            except ValueError:
                pass
        if cfg.get("mode2_detour_max"):
            try:
                MODE2_DETOUR_MINUTES_MAX = max(0, int(cfg["mode2_detour_max"]))
            except ValueError:
                pass
        if cfg.get("mode2_high_profit_threshold"):
            try:
                MODE2_HIGH_PROFIT_THRESHOLD = max(0, float(cfg["mode2_high_profit_threshold"]))
            except ValueError:
                pass
        if cfg.get("mode3_max_minutes_to_pickup"):
            try:
                MODE3_MAX_MINUTES_TO_PICKUP = max(1, int(cfg["mode3_max_minutes_to_pickup"]))
            except ValueError:
                pass
        if cfg.get("mode3_max_detour_minutes"):
            try:
                MODE3_MAX_DETOUR_MINUTES = max(0, int(cfg["mode3_max_detour_minutes"]))
            except ValueError:
                pass
        if cfg.get("response_timeout_seconds"):
            try:
                RESPONSE_TIMEOUT_SECONDS = max(60, int(cfg["response_timeout_seconds"]))
            except ValueError:
                pass
        if "response_page_base" in cfg:
            RESPONSE_PAGE_BASE = cfg["response_page_base"] or ""
        logger.info("已从 app_config 加载配置: baidu_ak=%s, driver_mode=%s", bool(BAIDU_AK), DRIVER_MODE)
    except Exception as e:
        logger.warning("从 app_config 加载配置失败: %s，使用默认值", e)


_load_app_config_from_db()
# ==========================================


# ---------------------------------------------------------------------------
# 一、核心数据模型 (Data Models)
# ---------------------------------------------------------------------------

class CurrentState(BaseModel):
    """当前状态：司机位置 + 已接订单的起终点列表 + 可选车牌（用于限行规避）"""
    driver_loc: str
    pickups: List[str]
    deliveries: List[str]
    plate_number: Optional[str] = None  # 车牌，如 沪A12345，供路线规划/评估时规避限行
    cartype: Optional[int] = None  # 0 燃油 1 纯电动，与 plate_number 配合


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
    """单条下次计划（新增或更新）"""
    origin: str
    destination: str
    departure_time: str   # 如 "06:00" 或 "2025-02-22 06:00"
    time_window_minutes: Optional[int] = 30   # 出发时间窗 ± 分钟
    min_orders: Optional[int] = 2
    max_orders: Optional[int] = 4


class PlannedTripUpdateWithIndex(PlannedTripUpdate):
    """更新指定索引的计划"""
    index: int


class GeocodeBatchRequest(BaseModel):
    """批量地理编码请求"""
    addresses: List[str]


class ReverseGeocodeRequest(BaseModel):
    """逆地理编码请求（经纬度 → 地址）"""
    lat: float
    lng: float


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


@app.get("/")
async def root() -> dict:
    """根路径，便于浏览器访问 88 或 /api 时看到服务正常。"""
    return {"service": "私人顺风车智能调度大脑", "status": "ok", "docs": "/docs"}


@app.get("/health")
async def health() -> dict:
    """健康检查，Nginx/监控可用。"""
    return {"status": "ok"}


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


def reverse_geocode(lat: float, lng: float) -> str:
    """
    逆地理编码：WGS84 经纬度 → 地址字符串。
    依赖：百度地图逆地理编码 API。
    """
    url = "https://api.map.baidu.com/reverse_geocoding/v3/"
    params = {
        "ak": BAIDU_AK,
        "output": "json",
        "coordtype": "wgs84ll",
        "location": f"{lat},{lng}",
    }
    try:
        resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        logger.error("百度逆地理编码请求异常: %s", e)
        raise HTTPException(
            status_code=503,
            detail=f"逆地理编码服务不可用: {e!s}",
        ) from e

    if data.get("status") != 0:
        msg = data.get("message", "未知错误")
        logger.warning("逆地理编码失败 [%s,%s]: %s", lat, lng, msg)
        raise HTTPException(
            status_code=400,
            detail=f"逆地理编码失败: {msg}",
        )

    result = data.get("result") or {}
    formatted = result.get("formatted_address") or result.get("sematic_description") or ""
    if not formatted and result.get("addressComponent"):
        ac = result["addressComponent"]
        parts = [
            ac.get("province"),
            ac.get("city"),
            ac.get("district"),
            ac.get("street"),
            ac.get("street_number"),
        ]
        formatted = "".join(p for p in parts if p)
    return formatted or f"{lat:.5f},{lng:.5f}"


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
    """百度 BD09 转 WGS84。路线数据已统一用 BD09，此函数仅保留供需要 WGS84 输出的场景（如导出）使用。"""
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


# 百度驾车 tactics：0 默认, 2 距离最短(不考虑限行), 5 躲避拥堵, 6 少收费, 12 距离优先(考虑限行), 13 时间优先
BAIDU_TACTICS_LEAST_TIME = 13
BAIDU_TACTICS_LEAST_DISTANCE = 12
BAIDU_TACTICS_LEAST_FEE = 6
BAIDU_TACTICS_AVOID_CONGESTION = 5


def _parse_one_route_path(route_obj: dict) -> List[List[float]]:
    """从单条 route 的 steps 解析出 path 点列 [lat, lng] BD09。"""
    path_bd09: List[List[float]] = []
    for step in route_obj.get("steps") or []:
        path_str = step.get("path")
        if not path_str:
            continue
        for part in path_str.split(";"):
            part = part.strip()
            if not part:
                continue
            seg = part.split(",")
            if len(seg) >= 2:
                try:
                    a, b = float(seg[0].strip()), float(seg[1].strip())
                    if 70 < a < 140 and 0 < b < 60:
                        lng_bd, lat_bd = a, b
                    else:
                        lat_bd, lng_bd = a, b
                    path_bd09.append([lat_bd, lng_bd])
                except (ValueError, TypeError):
                    continue
    return path_bd09


def _parse_one_route_steps(route_obj: dict) -> List[Dict[str, Any]]:
    """从单条 route 的 steps 解析出带道路名称的段落，供前端在路线上显示路名。返回 [{road_name, path}, ...]。"""
    out: List[Dict[str, Any]] = []
    for step in route_obj.get("steps") or []:
        path_str = step.get("path")
        if not path_str:
            continue
        path_bd09: List[List[float]] = []
        for part in path_str.split(";"):
            part = part.strip()
            if not part:
                continue
            seg = part.split(",")
            if len(seg) >= 2:
                try:
                    a, b = float(seg[0].strip()), float(seg[1].strip())
                    if 70 < a < 140 and 0 < b < 60:
                        lng_bd, lat_bd = a, b
                    else:
                        lat_bd, lng_bd = a, b
                    path_bd09.append([lat_bd, lng_bd])
                except (ValueError, TypeError):
                    continue
        if len(path_bd09) < 2:
            continue
        name = (step.get("road_name") or step.get("instruction") or "").strip()
        if not name or name == "无名路" or len(name) > 20:
            name = ""
        out.append({"road_name": name, "path": path_bd09})
    return out


def fetch_driving_route_path(
    route_coords_bd09: List[List[float]],
    plate_number: Optional[str] = None,
    cartype: Optional[int] = None,
    tactics: Optional[int] = None,
) -> Tuple[List[List[List[float]]], List[int], List[Dict[str, Any]]]:
    """
    调用百度驾车路线规划 Web API（direction/v2/driving），一次请求返回多条可选路线。
    返回 (所有路线的 path 列表, 每条路线的耗时秒数列表, 首条路线的 steps 含路名)。path 格式 [lat, lng] BD09。
    """
    if not route_coords_bd09 or len(route_coords_bd09) < 2:
        return [], [], []
    origin = f"{route_coords_bd09[0][0]},{route_coords_bd09[0][1]}"
    destination = f"{route_coords_bd09[-1][0]},{route_coords_bd09[-1][1]}"
    middle = route_coords_bd09[1:-1]
    if len(middle) > 18:
        middle = middle[:18]
    waypoints = "|".join(f"{c[0]},{c[1]}" for c in middle) if middle else None
    url = "https://api.map.baidu.com/direction/v2/driving"
    params: Dict[str, Any] = {
        "ak": BAIDU_AK,
        "origin": origin,
        "destination": destination,
        "coord_type": "bd09ll",
        "ret_coordtype": "bd09ll",
        "output": "json",
        "alternatives": 1,
    }
    if waypoints:
        params["waypoints"] = waypoints
    if tactics is not None and tactics in (0, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13):
        params["tactics"] = tactics
    plate = (plate_number or "").strip()
    if plate:
        params["plate_number"] = plate
        if cartype is not None and cartype in (0, 1):
            params["cartype"] = cartype
    try:
        resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        logger.warning("百度驾车路线规划请求异常: %s", e)
        return [], [], []

    if data.get("status") != 0:
        logger.warning("百度驾车路线规划失败: %s", data.get("message", "未知"))
        return [], [], []

    result = data.get("result") or {}
    routes = result.get("routes") or []
    if not routes:
        return [], [], []

    all_paths: List[List[List[float]]] = []
    all_durations: List[int] = []
    route_steps_first: List[Dict[str, Any]] = []
    for idx, r in enumerate(routes):
        path_bd09 = _parse_one_route_path(r)
        if len(path_bd09) >= 2:
            all_paths.append(path_bd09)
            dur = r.get("duration")
            if isinstance(dur, dict) and "value" in dur:
                dur = dur["value"]
            all_durations.append(int(dur) if isinstance(dur, (int, float)) else 0)
            if idx == 0:
                route_steps_first = _parse_one_route_steps(r)
    return all_paths, all_durations, route_steps_first


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


def solve_pdp_route_flexible(
    matrix: List[List[int]],
    pickup_delivery_pairs: List[Tuple[int, int]],
) -> Tuple[Optional[List[int]], int]:
    """
    支持「仅送」的 PDP：pickup_delivery_pairs 中每对 (接客点, 送客点) 先接后送；
    未出现在 pair 中的非起点节点仍会全部访问（通过 Disjunction 必选）。
    节点编号与 matrix 一致：0=司机起点，其余为途经点。
    返回：(最优路线节点索引列表, 总耗时秒数)；无解时 (None, 0)。
    """
    num_nodes = len(matrix)
    if num_nodes <= 1:
        return ([0] if num_nodes else [], 0)
    manager = pywrapcp.RoutingIndexManager(num_nodes, 1, 0)
    routing = pywrapcp.RoutingModel(manager)

    def duration_callback(from_index: int, to_index: int) -> int:
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        if to_node == 0:
            return 0
        return matrix[from_node][to_node]

    transit_callback_index = routing.RegisterTransitCallback(duration_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)
    routing.AddDimension(transit_callback_index, 0, 300000, True, "Time")
    time_dimension = routing.GetDimensionOrDie("Time")

    # 所有非起点节点必访（含仅送点）
    for node in range(1, num_nodes):
        routing.AddDisjunction([manager.NodeToIndex(node)], 0)
    for pickup_node, delivery_node in pickup_delivery_pairs:
        pickup_idx = manager.NodeToIndex(pickup_node)
        delivery_idx = manager.NodeToIndex(delivery_node)
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
    if not BARK_KEY or BARK_KEY == "bGPZAHqjNjdiQZTg5GeWWG":
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
# 模式1：多批次下次计划（探子/调度遍历 plans 按每条时间、地点找单）
# ---------------------------------------------------------------------------
def _plan_to_dict(p: Dict[str, Any]) -> dict:
    return {
        "origin": p.get("origin", ""),
        "destination": p.get("destination", ""),
        "departure_time": p.get("departure_time", ""),
        "time_window_minutes": p.get("time_window_minutes", 30),
        "min_orders": p.get("min_orders", 2),
        "max_orders": p.get("max_orders", 4),
        "completed": bool(p.get("completed")),
    }


def _sort_planned_trips() -> None:
    """未完成的按出发时间从早到晚排前，已结束找单的排后；计划不删，只结束找单任务。"""
    global planned_trips
    planned_trips.sort(
        key=lambda p: (
            bool(p.get("completed")),  # False 在前 = 未完成优先
            p.get("departure_time") or "",
            p.get("origin") or "",
            p.get("destination") or "",
        )
    )


@app.get("/planned_trip")
async def get_planned_trip() -> dict:
    """获取全部下次计划（多批次）。未结束找单的按出发时间从早到晚排前，已结束的排后。探子/调度用第一条 completed=false 的；计划不删只结束找单。"""
    _sort_planned_trips()
    return {"plans": [_plan_to_dict(p) for p in planned_trips]}


@app.post("/planned_trip")
async def add_planned_trip(body: PlannedTripUpdate) -> dict:
    """新增一条下次计划（找单任务未结束）。"""
    global planned_trips
    plan = {
        "origin": body.origin,
        "destination": body.destination,
        "departure_time": body.departure_time,
        "time_window_minutes": body.time_window_minutes or 30,
        "min_orders": body.min_orders or 2,
        "max_orders": body.max_orders or 4,
        "completed": False,
    }
    planned_trips.append(plan)
    _sort_planned_trips()
    logger.info("下次计划+1: %s -> %s, 出发 %s（共 %s 批）", body.origin, body.destination, body.departure_time, len(planned_trips))
    return {"plans": [_plan_to_dict(p) for p in planned_trips]}


@app.put("/planned_trip")
async def update_planned_trip(body: PlannedTripUpdateWithIndex) -> dict:
    """更新指定索引的一条下次计划（索引为排序后顺序，0=当前优先找单的一批）。"""
    global planned_trips
    _sort_planned_trips()
    i = body.index
    if i < 0 or i >= len(planned_trips):
        raise HTTPException(status_code=400, detail="index 越界")
    planned_trips[i] = {
        "origin": body.origin,
        "destination": body.destination,
        "departure_time": body.departure_time,
        "time_window_minutes": body.time_window_minutes or 30,
        "min_orders": body.min_orders or 2,
        "max_orders": body.max_orders or 4,
        "completed": planned_trips[i].get("completed", False),
    }
    _sort_planned_trips()
    logger.info("下次计划[%s]已更新: %s -> %s, 出发 %s", i, body.origin, body.destination, body.departure_time)
    return {"plans": [_plan_to_dict(p) for p in planned_trips]}


@app.post("/planned_trip/complete")
async def complete_planned_trip(index: int) -> dict:
    """结束指定索引的找单任务（计划保留不删，仅标记为已结束找单，探子/调度自动取下一条）。"""
    global planned_trips
    _sort_planned_trips()
    if index < 0 or index >= len(planned_trips):
        raise HTTPException(status_code=400, detail="index 越界")
    planned_trips[index]["completed"] = True
    logger.info("找单任务已结束: 第 %s 批（计划保留），下一批自动接上", index + 1)
    return {"plans": [_plan_to_dict(p) for p in planned_trips]}


# ---------------------------------------------------------------------------
# 网页地图：批量地理编码 + 当前路线预览（含经纬度，供地图绘制）
# ---------------------------------------------------------------------------
@app.post("/geocode_batch")
async def geocode_batch(body: GeocodeBatchRequest) -> list:
    """批量地理编码，返回 [{ address, lat, lng }, ...]（BD09 百度坐标系），失败项省略。"""
    out: List[dict] = []
    for addr in body.addresses:
        addr = (addr or "").strip()
        if not addr:
            continue
        try:
            coord_str = geocode_address(addr)
            lat_s, lng_s = coord_str.split(",", 1)
            lat_bd, lng_bd = float(lat_s), float(lng_s)
            out.append({"address": addr, "lat": lat_bd, "lng": lng_bd})
        except Exception as e:
            logger.warning("地理编码跳过 [%s]: %s", addr, e)
    return out


@app.post("/reverse_geocode")
async def reverse_geocode_endpoint(body: ReverseGeocodeRequest) -> dict:
    """逆地理编码：WGS84 经纬度 → 地址，供网页「刷新 GPS」后填入当前位置。"""
    address = reverse_geocode(body.lat, body.lng)
    return {"address": address, "lat": body.lat, "lng": body.lng}


@app.post("/current_route_preview")
async def current_route_preview(req: dict) -> dict:
    """
    根据当前状态计算最优路线，返回途经点地址顺序及经纬度，供网页地图绘制。
    请求体：{ "current_state": { "driver_loc", "pickups", "deliveries", "waypoints" } }, "tactics": 策略数字。
    """
    try:
        state = req.get("current_state") or {}
        driver_loc = (state.get("driver_loc") or "").strip()
        pickups = state.get("pickups") or []
        deliveries = state.get("deliveries") or []
        waypoints = state.get("waypoints") or []
        if isinstance(pickups, str):
            pickups = [s.strip() for s in pickups.split("\n") if s.strip()]
        if isinstance(deliveries, str):
            deliveries = [s.strip() for s in deliveries.split("\n") if s.strip()]
        if not isinstance(waypoints, list):
            waypoints = []
        waypoints = [str(w).strip() for w in waypoints if (w or "").strip()]
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"请求体格式错误: {e}") from e

    tactics = int(req.get("tactics", 0))

    if not driver_loc:
        raise HTTPException(status_code=400, detail="driver_loc 不能为空")
    if len(pickups) != len(deliveries):
        raise HTTPException(status_code=400, detail="pickups 与 deliveries 数量须一致")
    n = len(deliveries)
    m = len(waypoints)
    if n == 0 and m == 0:
        try:
            coord_str = geocode_address(driver_loc)
            lat_s, lng_s = coord_str.split(",", 1)
            lat_bd, lng_bd = float(lat_s), float(lng_s)
            return {
                "route_addresses": [driver_loc],
                "route_coords": [[lat_bd, lng_bd]],
                "point_types": ["driver"],
                "point_labels": ["司机"],
                "total_time_seconds": 0,
            }
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"地理编码失败: {e}") from e

    # 空 pickup 表示该乘客已上车，路线中排除该接客点；waypoints 为途经点（到达后前端删除）
    effective_pickups = [p for p in pickups if (p or "").strip()]
    k = len(effective_pickups)
    addresses = [driver_loc] + list(effective_pickups) + list(deliveries) + list(waypoints)
    coords = geocode_addresses(addresses)
    matrix = get_duration_matrix(coords)
    # 配对：仅对「未上车」的乘客建立接客->送客约束
    pickup_delivery_pairs: List[Tuple[int, int]] = []
    for i in range(n):
        if (pickups[i] or "").strip():
            pickup_ord = sum(1 for j in range(i) if (pickups[j] or "").strip())
            pickup_node = 1 + pickup_ord
            delivery_node = 1 + k + i
            pickup_delivery_pairs.append((pickup_node, delivery_node))
    route_indices, total_time = solve_pdp_route_flexible(matrix, pickup_delivery_pairs)
    if not route_indices:
        raise HTTPException(status_code=422, detail="无法规划出符合逻辑的路线")

    # 节点 0=司机, 1..k=接客, 1+k..1+k+n-1=送客, 1+k+n..1+k+n+m-1=途经点
    passengers_with_pickup = [i for i in range(n) if (pickups[i] or "").strip()]
    pickup_node_to_passenger = {1 + j: passengers_with_pickup[j] for j in range(k)}

    route_addresses = [addresses[i] for i in route_indices]
    point_types = []
    point_labels = []
    for i in route_indices:
        if i == 0:
            point_types.append("driver")
            point_labels.append("司机")
        elif 1 <= i <= k:
            point_types.append("pickup")
            point_labels.append(f"乘客{pickup_node_to_passenger[i] + 1}起点")
        elif k + 1 <= i <= k + n:
            point_types.append("delivery")
            point_labels.append(f"乘客{i - k}终点")
        else:
            point_types.append("waypoint")
            point_labels.append(f"途径点{i - k - n}")
    route_coords = []
    for i in route_indices:
        parts = coords[i].split(",", 1)
        lat_bd, lng_bd = float(parts[0]), float(parts[1])
        route_coords.append([lat_bd, lng_bd])

    # 调用百度驾车路线规划 Web API，获取沿道路的路径点，供地图画线（传车牌则规避限行，tactics 为策略）
    plate_number = (state.get("plate_number") or "").strip() or None
    cartype = state.get("cartype")
    if cartype is not None and cartype not in (0, 1):
        cartype = None
    if tactics not in (0, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13):
        tactics = 0
    all_paths: List[List[List[float]]] = []
    route_durations: List[int] = []
    route_steps: List[Dict[str, Any]] = []
    try:
        all_paths, route_durations, route_steps = fetch_driving_route_path(
            route_coords, plate_number=plate_number, cartype=cartype, tactics=tactics
        )
    except Exception as e:
        logger.warning("获取驾车路径失败（前端将用站点折线或分段规划）: %s", e)

    return {
        "route_addresses": route_addresses,
        "route_coords": route_coords,
        "route_paths": all_paths,
        "route_durations": route_durations,
        "route_steps": route_steps,
        "point_types": point_types,
        "point_labels": point_labels,
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
        # 附近接力（mode3）下放弃且不再接单 → 开启计划寻找（mode1），否则暂停
        if DRIVER_MODE == "mode3":
            DRIVER_MODE = "mode1"
            logger.info("用户放弃接力任务且不再接单，已切换为计划寻找（mode1）")
        else:
            DRIVER_MODE = "pause"
            logger.info("用户选择不再接单，已切换为 pause")

    if ac and cont:
        return {"ok": True, "message": "已记录接单，将继续为你推送顺路单（模式2）"}
    if ac and not cont:
        return {"ok": True, "message": "已记录接单，已暂停推送；需要时请手动切回模式2"}
    if not ac and cont:
        return {"ok": True, "message": "已放弃该单并不再推送此单，将继续推送其他顺路单"}
    if not ac and not cont and DRIVER_MODE == "mode1":
        return {"ok": True, "message": "已放弃接力任务，已切换为计划寻找；探子将按下次计划找单"}
    return {"ok": True, "message": "已放弃该单并暂停推送；需要时请手动切回"}


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
