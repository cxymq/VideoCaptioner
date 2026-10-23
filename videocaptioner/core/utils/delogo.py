"""去水印：解析水印区域并生成 FFmpeg delogo 滤镜

区域格式为 "x,y,w,h"，单位是原视频像素，多个区域用 ";" 分隔，例如：
    "1560,25,345,80;20,20,200,60"
"""

import re
from typing import List, Optional, Tuple

from videocaptioner.core.utils.logger import setup_logger

logger = setup_logger("delogo")

DelogoRegion = Tuple[int, int, int, int]

_REGION_RE = re.compile(r"^\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*$")


def parse_delogo_regions(spec: Optional[str]) -> List[DelogoRegion]:
    """解析区域字符串，格式错误时抛出 ValueError"""
    if not spec or not spec.strip():
        return []

    regions: List[DelogoRegion] = []
    for part in re.split(r"[;\n]", spec):
        if not part.strip():
            continue
        match = _REGION_RE.match(part)
        if not match:
            raise ValueError(f"Invalid delogo region '{part.strip()}', expected x,y,w,h")
        x, y, w, h = (int(v) for v in match.groups())
        if w <= 0 or h <= 0:
            raise ValueError(f"Invalid delogo region '{part.strip()}', width and height must be > 0")
        regions.append((x, y, w, h))
    return regions


def build_delogo_filter(regions: Optional[List[DelogoRegion]], width: int, height: int) -> str:
    """生成 delogo 滤镜链，无有效区域时返回空字符串

    FFmpeg 的 delogo 要求区域四边都与画面边缘保留至少 1 像素，
    这里自动把区域收进画面内，完全落在画面外的区域会被忽略。
    """
    filters = []
    for x, y, w, h in regions or []:
        x0, y0 = max(x, 1), max(y, 1)
        x1, y1 = min(x + w, width - 1), min(y + h, height - 1)
        if x1 - x0 < 1 or y1 - y0 < 1:
            logger.warning(f"Delogo region {(x, y, w, h)} is outside {width}x{height}, skipped")
            continue
        filters.append(f"delogo=x={x0}:y={y0}:w={x1 - x0}:h={y1 - y0}")
    return ",".join(filters)
