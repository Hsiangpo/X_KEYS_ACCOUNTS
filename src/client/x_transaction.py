"""In-repo generator for X x-client-transaction-id header."""

from __future__ import annotations

import base64
import hashlib
import math
import random
import re
import time
from functools import reduce
from typing import Any

import bs4


DEFAULT_RANDOM_KEYWORD = "obfiowerehiring"
DEFAULT_ADDITIONAL_RANDOM_NUMBER = 3
ON_DEMAND_FILE_URL = "https://abs.twimg.com/responsive-web/client-web/ondemand.s.{filename}a.js"
ON_DEMAND_FILE_REGEX = re.compile(
    r"""['|\"]{1}ondemand\.s['|\"]{1}:\s*['|\"]{1}([\w]*)['|\"]{1}""",
    flags=(re.VERBOSE | re.MULTILINE),
)
INDICES_REGEX = re.compile(r"""(\(\w{1}\[(\d{1,2})\],\s*16\))+""", flags=(re.VERBOSE | re.MULTILINE))


class Cubic:
    def __init__(self, curves: list[float]):
        self.curves = curves

    def get_value(self, target_time: float) -> float:
        start_gradient = 0.0
        end_gradient = 0.0
        start = 0.0
        middle = 0.0
        end = 1.0

        if target_time <= 0.0:
            if self.curves[0] > 0.0:
                start_gradient = self.curves[1] / self.curves[0]
            elif self.curves[1] == 0.0 and self.curves[2] > 0.0:
                start_gradient = self.curves[3] / self.curves[2]
            return start_gradient * target_time

        if target_time >= 1.0:
            if self.curves[2] < 1.0:
                end_gradient = (self.curves[3] - 1.0) / (self.curves[2] - 1.0)
            elif self.curves[2] == 1.0 and self.curves[0] < 1.0:
                end_gradient = (self.curves[1] - 1.0) / (self.curves[0] - 1.0)
            return 1.0 + end_gradient * (target_time - 1.0)

        while start < end:
            middle = (start + end) / 2
            x_estimate = self._calculate(self.curves[0], self.curves[2], middle)
            if abs(target_time - x_estimate) < 0.00001:
                return self._calculate(self.curves[1], self.curves[3], middle)
            if x_estimate < target_time:
                start = middle
            else:
                end = middle
        return self._calculate(self.curves[1], self.curves[3], middle)

    @staticmethod
    def _calculate(first: float, second: float, middle: float) -> float:
        return (
            3.0 * first * (1 - middle) * (1 - middle) * middle
            + 3.0 * second * (1 - middle) * middle * middle
            + middle * middle * middle
        )


def parse_home_page_html(html: str) -> bs4.BeautifulSoup:
    return bs4.BeautifulSoup(html, "html.parser")


def extract_ondemand_file_url(home_page: bs4.BeautifulSoup) -> str | None:
    match = ON_DEMAND_FILE_REGEX.search(str(home_page))
    if not match:
        return None
    return ON_DEMAND_FILE_URL.format(filename=match.group(1))


class XClientTransaction:
    """Generate x-client-transaction-id with in-repo algorithm."""

    def __init__(
        self,
        *,
        home_page: bs4.BeautifulSoup,
        ondemand_script: str,
        random_keyword: str = DEFAULT_RANDOM_KEYWORD,
        random_number: int = DEFAULT_ADDITIONAL_RANDOM_NUMBER,
    ) -> None:
        if not isinstance(home_page, bs4.BeautifulSoup):
            raise TypeError(f"home_page must be BeautifulSoup, got: {type(home_page).__name__}")
        if not isinstance(ondemand_script, str):
            raise TypeError(f"ondemand_script must be str, got: {type(ondemand_script).__name__}")

        self.home_page = home_page
        self.ondemand_script = ondemand_script
        self.random_keyword = random_keyword
        self.random_number = random_number

        self.row_index, self.key_byte_indices = self._extract_indices(self.ondemand_script)
        self.key = self._extract_site_verification_key(self.home_page)
        self.key_bytes = list(base64.b64decode(bytes(self.key, "utf-8")))
        self.animation_key = self._build_animation_key(self.key_bytes, self.home_page)

    def generate_transaction_id(
        self,
        *,
        method: str,
        path: str,
        time_now: int | None = None,
        random_num: int | None = None,
    ) -> str:
        unix_delta_seconds = time_now or math.floor((time.time() * 1000 - 1682924400 * 1000) / 1000)
        time_now_bytes = [(unix_delta_seconds >> (index * 8)) & 0xFF for index in range(4)]
        hash_digest = hashlib.sha256(
            f"{method}!{path}!{unix_delta_seconds}{self.random_keyword}{self.animation_key}".encode()
        ).digest()
        digest_bytes = list(hash_digest)
        random_byte = random_num if random_num is not None else random.randint(0, 255)
        payload = [*self.key_bytes, *time_now_bytes, *digest_bytes[:16], self.random_number]
        obfuscated = bytearray([random_byte, *[item ^ random_byte for item in payload]])
        return base64.b64encode(obfuscated).decode().strip("=")

    @staticmethod
    def _extract_indices(ondemand_script: str) -> tuple[int, list[int]]:
        candidates: list[int] = []
        for match in INDICES_REGEX.finditer(ondemand_script):
            candidates.append(int(match.group(2)))
        if not candidates:
            raise RuntimeError("Could not extract key-byte indices from ondemand script.")
        return candidates[0], candidates[1:]

    @staticmethod
    def _extract_site_verification_key(home_page: bs4.BeautifulSoup) -> str:
        element = home_page.select_one("meta[name='twitter-site-verification']")
        if not element:
            raise RuntimeError("Could not find twitter-site-verification meta key.")
        value = element.get("content")
        if not value:
            raise RuntimeError("twitter-site-verification key is empty.")
        return str(value)

    @staticmethod
    def _extract_frames(home_page: bs4.BeautifulSoup) -> list[bs4.Tag]:
        frames = list(home_page.select("[id^='loading-x-anim']"))
        if not frames:
            raise RuntimeError("Could not find loading-x-anim frames in home page.")
        return frames

    @staticmethod
    def _extract_frame_number_rows(frame: bs4.Tag) -> list[list[int]]:
        first_layer_children = list(frame.children)
        if not first_layer_children:
            raise RuntimeError("loading-x-anim frame has no children.")

        second_layer_children = list(first_layer_children[0].children)
        if len(second_layer_children) < 2:
            raise RuntimeError("loading-x-anim frame is missing expected path nodes.")

        target_path = second_layer_children[1].get("d")
        if not target_path or len(str(target_path)) <= 9:
            raise RuntimeError("loading-x-anim path data is empty.")

        rows: list[list[int]] = []
        for row in str(target_path)[9:].split("C"):
            values = re.sub(r"[^\d]+", " ", row).strip().split()
            if values:
                rows.append([int(value) for value in values])
        if not rows:
            raise RuntimeError("Could not parse animation frame rows.")
        return rows

    def _build_animation_key(self, key_bytes: list[int], home_page: bs4.BeautifulSoup) -> str:
        row_index = key_bytes[self.row_index] % 16
        frame_time_seed = reduce(
            lambda left, right: left * right,
            [key_bytes[index] % 16 for index in self.key_byte_indices],
        )
        frame_time = _js_round(frame_time_seed / 10) * 10

        frames = self._extract_frames(home_page)
        selected_frame = frames[key_bytes[5] % 4]
        rows = self._extract_frame_number_rows(selected_frame)
        if row_index >= len(rows):
            raise RuntimeError("Animation row index out of range.")
        target_row = rows[row_index]
        if len(target_row) < 11:
            raise RuntimeError("Animation row has insufficient data points.")

        target_time = float(frame_time) / 4096
        return self._animate(target_row, target_time)

    def _animate(self, frames: list[int], target_time: float) -> str:
        from_color = [float(item) for item in [*frames[:3], 1]]
        to_color = [float(item) for item in [*frames[3:6], 1]]
        from_rotation = [0.0]
        to_rotation = [_solve(float(frames[6]), 60.0, 360.0, rounding=True)]
        easing_values = [_solve(float(value), _odd_floor(index), 1.0, rounding=False) for index, value in enumerate(frames[7:])]
        if len(easing_values) < 4:
            raise RuntimeError("Animation easing values are incomplete.")

        cubic = Cubic(easing_values[:4])
        progress = cubic.get_value(target_time)
        color = _interpolate(from_color, to_color, progress)
        clamped_color = [max(0, min(255, value)) for value in color]
        rotation = _interpolate(from_rotation, to_rotation, progress)
        matrix = _rotation_to_matrix(rotation[0])

        serialized: list[str] = [format(round(value), "x") for value in clamped_color[:-1]]
        for value in matrix:
            rounded = abs(round(value, 2))
            hex_value = _float_to_hex(rounded)
            if hex_value.startswith("."):
                serialized.append(f"0{hex_value}".lower())
            else:
                serialized.append(hex_value.lower() if hex_value else "0")
        serialized.extend(["0", "0"])
        return re.sub(r"[.-]", "", "".join(serialized))


def _js_round(value: float) -> float:
    rounded_down = math.floor(value)
    if value - rounded_down >= 0.5:
        rounded_down = math.ceil(value)
    return math.copysign(rounded_down, value)


def _solve(value: float, minimum: float, maximum: float, *, rounding: bool) -> float:
    scaled = value * (maximum - minimum) / 255 + minimum
    return math.floor(scaled) if rounding else round(scaled, 2)


def _odd_floor(index: int) -> float:
    return -1.0 if index % 2 else 0.0


def _interpolate(start: list[float], end: list[float], ratio: float) -> list[float]:
    if len(start) != len(end):
        raise RuntimeError("Interpolation input length mismatch.")
    return [start_value * (1 - ratio) + end_value * ratio for start_value, end_value in zip(start, end)]


def _rotation_to_matrix(degrees: float) -> list[float]:
    radians = math.radians(degrees)
    return [math.cos(radians), -math.sin(radians), math.sin(radians), math.cos(radians)]


def _float_to_hex(value: float, *, max_fraction_digits: int = 24) -> str:
    result: list[str] = []
    quotient = int(value)
    fraction = value - quotient

    while quotient > 0:
        quotient = int(value / 16)
        remainder = int(value - (float(quotient) * 16))
        result.insert(0, chr(remainder + 55) if remainder > 9 else str(remainder))
        value = float(quotient)

    if fraction == 0:
        return "".join(result)

    result.append(".")
    fraction_digits = 0
    while fraction > 0 and fraction_digits < max_fraction_digits:
        fraction *= 16
        integer_part = int(fraction)
        fraction -= float(integer_part)
        result.append(chr(integer_part + 55) if integer_part > 9 else str(integer_part))
        fraction_digits += 1

    return "".join(result)


def _debug_context_payload(context: XClientTransaction) -> dict[str, Any]:
    """Helper for local diagnostics."""
    return {
        "row_index": context.row_index,
        "key_byte_indices": list(context.key_byte_indices),
        "key_len": len(context.key_bytes),
        "animation_key_len": len(context.animation_key),
    }

