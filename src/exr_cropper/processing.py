from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Region:
    x: int
    y: int
    width: int
    height: int

    def validate(self, image_width: int, image_height: int) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("Crop width and height must be greater than zero.")
        if self.x < 0 or self.y < 0:
            raise ValueError("Crop origin must be inside the image.")
        if self.x + self.width > image_width or self.y + self.height > image_height:
            raise ValueError(
                f"Crop {self} is outside image bounds {image_width}x{image_height}."
            )

    def clamped(self, image_width: int, image_height: int) -> "Region":
        if image_width <= 0 or image_height <= 0:
            return Region(0, 0, 1, 1)

        x = min(max(self.x, 0), image_width - 1)
        y = min(max(self.y, 0), image_height - 1)
        width = min(max(self.width, 1), image_width - x)
        height = min(max(self.height, 1), image_height - y)
        return Region(x, y, width, height)

    def suffix(self) -> str:
        return f"x{self.x}_y{self.y}_w{self.width}_h{self.height}"


def crop_channels(
    channels: dict[str, np.ndarray],
    region: Region,
    image_width: int,
    image_height: int,
) -> dict[str, np.ndarray]:
    region.validate(image_width, image_height)

    cropped: dict[str, np.ndarray] = {}
    for name, pixels in channels.items():
        if pixels.shape[:2] != (image_height, image_width):
            raise ValueError(
                f"Channel {name!r} has shape {pixels.shape}; subsampled channels are not supported."
            )
        y0 = region.y
        y1 = region.y + region.height
        x0 = region.x
        x1 = region.x + region.width
        cropped[name] = np.ascontiguousarray(pixels[y0:y1, x0:x1], dtype=np.float32)
    return cropped


def tonemap_rgb(rgb: np.ndarray, exposure_stops: float = 0.0, gamma: float = 2.2) -> np.ndarray:
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("RGB image must have shape (height, width, 3).")
    if gamma <= 0:
        raise ValueError("Gamma must be greater than zero.")

    scaled = np.asarray(rgb, dtype=np.float32) * float(2.0**exposure_stops)
    scaled = np.nan_to_num(scaled, nan=0.0, posinf=1.0, neginf=0.0)
    scaled = np.clip(scaled, 0.0, 1.0)
    encoded = np.power(scaled, 1.0 / gamma)
    return np.clip(encoded * 255.0 + 0.5, 0, 255).astype(np.uint8)


def rgb_from_channels(channels: dict[str, np.ndarray]) -> np.ndarray:
    names = find_rgb_channel_names(channels)
    rgb = np.dstack([channels[name] for name in names]).astype(np.float32, copy=False)
    return np.ascontiguousarray(rgb)


def find_rgb_channel_names(channels: dict[str, np.ndarray]) -> tuple[str, str, str]:
    if all(name in channels for name in ("R", "G", "B")):
        return ("R", "G", "B")

    layers: dict[str, dict[str, str]] = {}
    for name in channels:
        if "." not in name:
            continue
        prefix, component = name.rsplit(".", 1)
        if component in {"R", "G", "B"}:
            layers.setdefault(prefix, {})[component] = name

    for prefix in sorted(layers):
        layer = layers[prefix]
        if all(component in layer for component in ("R", "G", "B")):
            return (layer["R"], layer["G"], layer["B"])

    raise ValueError("The EXR must contain R, G, and B channels for PNG preview/export.")
