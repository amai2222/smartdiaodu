import base64
import re
import time
from typing import Any, Dict, List, Optional

import requests


class BaiduOcrClient:
    """百度 OCR 轻量封装：自动获取/缓存 access_token。"""

    def __init__(self, api_key: str, secret_key: str, timeout: int = 8) -> None:
        self.api_key = (api_key or "").strip()
        self.secret_key = (secret_key or "").strip()
        self.timeout = timeout
        self._access_token: str = ""
        self._expire_at: float = 0.0

    def available(self) -> bool:
        return bool(self.api_key and self.secret_key)

    def _get_access_token(self) -> str:
        now = time.time()
        if self._access_token and now < self._expire_at - 60:
            return self._access_token
        url = "https://aip.baidubce.com/oauth/2.0/token"
        params = {
            "grant_type": "client_credentials",
            "client_id": self.api_key,
            "client_secret": self.secret_key,
        }
        resp = requests.post(url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json() or {}
        token = (data.get("access_token") or "").strip()
        if not token:
            raise RuntimeError(f"百度 OCR 获取 access_token 失败: {data}")
        expires_in = int(data.get("expires_in") or 0)
        self._access_token = token
        self._expire_at = now + max(300, expires_in)
        return token

    @staticmethod
    def _normalize_image_base64(image_base64: str) -> str:
        s = (image_base64 or "").strip()
        if not s:
            return ""
        if s.startswith("data:"):
            parts = s.split(",", 1)
            if len(parts) == 2:
                s = parts[1]
        return s

    def ocr_text_lines(self, image_base64: str) -> List[str]:
        if not self.available():
            raise RuntimeError("未配置百度 OCR API Key/Secret")
        payload_image = self._normalize_image_base64(image_base64)
        if not payload_image:
            return []
        # 先做一次 base64 合法性检查，避免无效图片请求 OCR。
        base64.b64decode(payload_image, validate=True)
        token = self._get_access_token()
        url = f"https://aip.baidubce.com/rest/2.0/ocr/v1/accurate_basic?access_token={token}"
        data = {
            "image": payload_image,
            "detect_direction": "true",
            "paragraph": "false",
            "probability": "true",
        }
        resp = requests.post(
            url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        out = resp.json() or {}
        words_result = out.get("words_result") or []
        lines: List[str] = []
        for item in words_result:
            text = (item.get("words") or "").strip()
            if text:
                lines.append(text)
        return lines

    def ocr_text_lines_from_bytes(self, image_bytes: bytes) -> List[str]:
        """文件字节 OCR：内部转 base64 后复用同一识别逻辑。"""
        if not image_bytes:
            return []
        payload = base64.b64encode(image_bytes).decode("ascii")
        return self.ocr_text_lines(payload)


def _normalize_text(s: str) -> str:
    s = (s or "").strip()
    s = s.replace("：", ":").replace("；", ";")
    s = s.replace("（", "(").replace("）", ")")
    s = re.sub(r"\s+", " ", s)
    return s


_OCR_ADDRESS_FIXUPS = {
    "巿": "市",
    "縣": "县",
    "區": "区",
    "鎮": "镇",
    "浦东新": "浦东新区",
    "黄浦区人民大道185号人民广埸": "黄浦区人民大道185号人民广场",
    "上海虹桥綜合交通枢纽": "上海虹桥综合交通枢纽",
}


def _normalize_address_candidate(addr: str) -> str:
    s = _normalize_text(addr)
    s = re.sub(r"^(?:起点|上车点|出发地|终点|下车点|目的地)\s*[:：]?\s*", "", s)
    s = s.strip(" -;,.，。")
    for bad, good in _OCR_ADDRESS_FIXUPS.items():
        s = s.replace(bad, good)
    # 规整常见 OCR 混淆：如“浦东新 区”/“浦东新.区”
    s = re.sub(r"浦东新[\s\.\-]*区", "浦东新区", s)
    # 清洗 OCR 连写噪声：如“区区”“市市”“县县”。
    s = re.sub(r"(省|市|区|县|镇)\1+", r"\1", s)
    s = re.sub(r"\s+", "", s) if len(s) <= 22 else re.sub(r"\s+", " ", s)
    return s.strip()


def _extract_price(text: str) -> Optional[float]:
    m = re.search(r"(?:¥|￥|收益|车费|价格)\s*[:：]?\s*(\d+(?:\.\d+)?)", text)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    m2 = re.search(r"(\d+(?:\.\d+)?)\s*元", text)
    if m2:
        try:
            return float(m2.group(1))
        except ValueError:
            return None
    return None


def _extract_departure_time(text: str) -> Optional[str]:
    """提取出发时间，返回 HH:MM；提取不到返回 None。"""
    m = re.search(r"\b([01]?\d|2[0-3])\s*:\s*([0-5]\d)\b", text)
    if m:
        hh = int(m.group(1))
        mm = int(m.group(2))
        return f"{hh:02d}:{mm:02d}"
    m2 = re.search(r"([01]?\d|2[0-3])\s*点\s*([0-5]?\d)?\s*分?", text)
    if m2:
        hh = int(m2.group(1))
        mm = int(m2.group(2) or 0)
        return f"{hh:02d}:{mm:02d}"
    return None


def _infer_platform(lines: List[str], platform_hint: Optional[str] = None) -> str:
    hint = (platform_hint or "").strip().lower()
    if hint in ("hello", "didi"):
        return hint
    text = " ".join([_normalize_text(x) for x in (lines or [])])
    if re.search(r"(邀请同行|立即同行|超级顺路|车主分送)", text):
        return "didi"
    if re.search(r"(顺路订单|拼座|愿意协商高速费|不承担高速费)", text):
        return "hello"
    return "unknown"


def _extract_toll_negotiable(text: str) -> Optional[bool]:
    t = _normalize_text(text)
    if not t:
        return None
    if re.search(r"(不愿意|不同意|不接受|拒绝)\s*协商?\s*高速费", t):
        return False
    if re.search(r"不承担高速费", t):
        return False
    if re.search(r"(可以|愿意|可|能)\s*协商?\s*高速费", t):
        return True
    if re.search(r"高速费\s*(可协商|可议|可谈)", t):
        return True
    return None


def _normalize_card_line_address(line: str) -> str:
    s = _normalize_text(line)
    # 去掉卡片里常见尾部距离噪音，如 32.6km / <1km
    s = re.sub(r"(<\s*\d+(?:\.\d+)?\s*km|\d+(?:\.\d+)?\s*km)\s*$", "", s, flags=re.I)
    s = s.strip(" -;,.，。")
    return _normalize_address_candidate(s)


def _extract_driver_region_prefix(driver_loc: str) -> str:
    s = _normalize_text(driver_loc or "")
    if not s:
        return ""
    m = re.search(r"^(?:(.*?省))?(.*?市)(.*?(?:区|县|市))?", s)
    if not m:
        return ""
    prov = (m.group(1) or "").strip()
    city = (m.group(2) or "").strip()
    dist = (m.group(3) or "").strip()
    return (prov + city + dist).strip()


def _is_card_noise_line(line: str) -> bool:
    return bool(
        re.search(
            r"(元|奖励|拼座|独享|订单里程|查看过|邀请同行|立即同行|收到邀请|已预付|可协商高速费|可以协商高速费|愿意协商高速费|不承担高速费|已支付|愿拼)",
            line,
        )
    )


def _is_card_addr_anchor(line: str) -> bool:
    if re.search(r"^\s*距你\s*\d+(?:\.\d+)?\s*km", line, flags=re.I):
        return True
    if "·" in line:
        return True
    # 兜底：纯行政区划短语（避免把“小区xx栋”误判为锚点）
    if re.search(r"(?:省|市|区|县|镇|新区)$", line) and len(line) <= 16:
        return True
    return False


def _join_region_detail(region_line: str, detail_line: str, driver_region_prefix: str) -> str:
    region = _normalize_card_line_address(region_line or "")
    detail = _normalize_card_line_address(detail_line or "")
    if re.search(r"^\s*距你\s*\d+(?:\.\d+)?\s*km", region_line or "", flags=re.I):
        if detail and driver_region_prefix:
            return _normalize_address_candidate(driver_region_prefix + detail)
        return detail
    if region and detail:
        if detail in region:
            return region
        return _normalize_address_candidate(region + detail)
    return region or detail


def _extract_card_candidates(
    lines: List[str],
    max_cards: int = 3,
    platform_hint: Optional[str] = None,
    driver_loc: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """针对哈啰/滴滴卡片流做提取，每张图最多提取 max_cards 个卡片。"""
    if not lines:
        return []
    platform = _infer_platform(lines, platform_hint=platform_hint)
    driver_region_prefix = _extract_driver_region_prefix(driver_loc or "")
    norm_lines = [_normalize_text(x) for x in lines if _normalize_text(x)]
    header_re = re.compile(r"^\s*\d{1,3}\s*%\s*(?:顺路|超级顺路)")
    headers: List[int] = [i for i, t in enumerate(norm_lines) if header_re.search(t)]
    if not headers:
        return []

    out: List[Dict[str, Any]] = []
    for h_idx, start in enumerate(headers[:max_cards]):
        end = headers[h_idx + 1] if (h_idx + 1) < len(headers) else len(norm_lines)
        block = norm_lines[start:end]
        if not block:
            continue

        dep_time = _extract_departure_time(block[0])
        price: Optional[float] = None
        toll_negotiable: Optional[bool] = None
        for ln in block:
            p = _extract_price(ln)
            if p is not None:
                price = p
            tn = _extract_toll_negotiable(ln)
            if tn is not None:
                toll_negotiable = tn

        # 滴滴规则：没有“高速费”字样时，按“不承担高速费”处理
        if platform == "didi" and toll_negotiable is None:
            toll_negotiable = False

        # 抓取卡片中的地址锚点（起点锚点+终点锚点），并拼接下一行详细地址。
        addr_part_lines = [ln for ln in block[1:] if ln and not _is_card_noise_line(ln)]
        anchors: List[int] = [i for i, ln in enumerate(addr_part_lines) if _is_card_addr_anchor(ln)]
        if len(anchors) < 2:
            continue
        pickup_anchor_idx = anchors[0]
        delivery_anchor_idx = anchors[1]

        pickup_region = addr_part_lines[pickup_anchor_idx]
        delivery_region = addr_part_lines[delivery_anchor_idx]

        pickup_detail = ""
        for j in range(pickup_anchor_idx + 1, len(addr_part_lines)):
            if _is_card_addr_anchor(addr_part_lines[j]):
                break
            pickup_detail = addr_part_lines[j]
            break

        delivery_detail = ""
        for j in range(delivery_anchor_idx + 1, len(addr_part_lines)):
            if _is_card_addr_anchor(addr_part_lines[j]):
                break
            delivery_detail = addr_part_lines[j]
            break

        pickup_addr = _join_region_detail(pickup_region, pickup_detail, driver_region_prefix)
        delivery_addr = _join_region_detail(delivery_region, delivery_detail, driver_region_prefix)
        if not pickup_addr or not delivery_addr:
            continue

        out.append(
            {
                "pickup": pickup_addr,
                "delivery": delivery_addr,
                "price": price,
                "departure_time": dep_time,
                "toll_negotiable": toll_negotiable,
                "source_text": " | ".join(block),
                "source_platform": platform,
            }
        )

    return out


def extract_passenger_candidates(
    lines: List[str], platform_hint: Optional[str] = None, driver_loc: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    从 OCR 行文本提取候选乘客起终点：
    - 支持同一行出现「起点/终点」
    - 支持多行配对
    """
    # 先走卡片识别逻辑（哈啰/滴滴），每图最多取 3 张卡片。
    card_out = _extract_card_candidates(lines, max_cards=3, platform_hint=platform_hint, driver_loc=driver_loc)
    if card_out:
        out = card_out
    else:
        out: List[Dict[str, Any]] = []
    pending_pickup: Optional[str] = None
    pending_price: Optional[float] = None
    pending_departure_time: Optional[str] = None
    pending_toll_negotiable: Optional[bool] = None

    if not card_out:
        for raw in lines:
            line = _normalize_text(raw)
            if not line:
                continue
            price = _extract_price(line)
            if price is not None:
                pending_price = price
            dep = _extract_departure_time(line)
            if dep and re.search(r"(出发|上车|发车|最晚|约(?:定)?|预计|时间)", line):
                pending_departure_time = dep
            tn = _extract_toll_negotiable(line)
            if tn is not None:
                pending_toll_negotiable = tn

            both = re.search(r"起点\s*[:：]?\s*(.+?)\s*终点\s*[:：]?\s*(.+)$", line)
            if both:
                pickup = _normalize_address_candidate(both.group(1))
                delivery = _normalize_address_candidate(both.group(2))
                if pickup and delivery:
                    out.append(
                        {
                            "pickup": pickup,
                            "delivery": delivery,
                            "price": pending_price,
                            "departure_time": pending_departure_time,
                            "toll_negotiable": pending_toll_negotiable,
                            "source_text": raw,
                        }
                    )
                    pending_pickup = None
                    pending_price = None
                    pending_departure_time = None
                    pending_toll_negotiable = None
                    continue

            m_pick = re.search(r"(?:起点|上车点|出发地)\s*[:：]?\s*(.+)$", line)
            if m_pick:
                pending_pickup = _normalize_address_candidate(m_pick.group(1))
                continue

            m_del = re.search(r"(?:终点|下车点|目的地)\s*[:：]?\s*(.+)$", line)
            if m_del:
                delivery = _normalize_address_candidate(m_del.group(1))
                if pending_pickup and delivery:
                    out.append(
                        {
                            "pickup": pending_pickup,
                            "delivery": delivery,
                            "price": pending_price,
                            "departure_time": pending_departure_time,
                            "toll_negotiable": pending_toll_negotiable,
                            "source_text": raw,
                        }
                    )
                    pending_pickup = None
                    pending_price = None
                    pending_departure_time = None
                    pending_toll_negotiable = None
                continue

    # 去重：保留起终点相同但出发时间/金额不同的候选，避免信息损失。
    dedup: List[Dict[str, Any]] = []
    seen = set()
    for c in out:
        key = (
            c.get("pickup", "").strip(),
            c.get("delivery", "").strip(),
            c.get("departure_time", "").strip(),
            "" if c.get("price") is None else str(c.get("price")),
            "" if c.get("toll_negotiable") is None else str(bool(c.get("toll_negotiable"))),
        )
        if not key[0] or not key[1]:
            continue
        if key in seen:
            continue
        seen.add(key)
        dedup.append(c)
    return dedup
