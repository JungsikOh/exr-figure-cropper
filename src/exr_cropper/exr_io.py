from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import OpenEXR
from PIL import Image, ImageDraw

from .processing import Region, crop_channels, rgb_from_channels, tonemap_rgb


@dataclass
class ExrImage:
    path: Path
    width: int
    height: int
    channels: dict[str, np.ndarray]
    header: dict


def read_exr(path: str | Path) -> ExrImage:
    exr_path = Path(path)
    try:
        exr_file = OpenEXR.File(str(exr_path), separate_channels=True)
    except Exception as exc:  # OpenEXR raises its own pybind exception type.
        raise ValueError(f"Failed to read EXR file: {exr_path}") from exc

    channels: dict[str, np.ndarray] = {}
    for name, channel in exr_file.channels().items():
        pixels = np.asarray(channel.pixels)
        if pixels.ndim != 2:
            raise ValueError(f"Channel {name!r} is not a 2D image channel.")
        channels[name] = np.ascontiguousarray(pixels)

    if not channels:
        raise ValueError(f"EXR file has no image channels: {exr_path}")

    first = next(iter(channels.values()))
    height, width = first.shape
    for name, pixels in channels.items():
        if pixels.shape != (height, width):
            raise ValueError(
                f"Channel {name!r} has shape {pixels.shape}; all channels must share one resolution."
            )

    return ExrImage(
        path=exr_path,
        width=width,
        height=height,
        channels=channels,
        header=dict(exr_file.header()),
    )


def write_exr(path: str | Path, channels: dict[str, np.ndarray], source_header: dict | None = None) -> None:
    if not channels:
        raise ValueError("Cannot write an EXR with no channels.")

    first = next(iter(channels.values()))
    if first.ndim != 2:
        raise ValueError("EXR channels must be 2D arrays.")

    height, width = first.shape
    out_channels: dict[str, np.ndarray] = {}
    for name, pixels in channels.items():
        if pixels.shape != (height, width):
            raise ValueError("All output EXR channels must have the same shape.")
        out_channels[name] = np.ascontiguousarray(pixels, dtype=np.float32)

    header = {
        "compression": (source_header or {}).get("compression", OpenEXR.ZIP_COMPRESSION),
        "type": OpenEXR.scanlineimage,
    }
    OpenEXR.File(header, out_channels).write(str(path))


def save_png(path: str | Path, channels: dict[str, np.ndarray], exposure_stops: float = 0.0) -> None:
    rgb = rgb_from_channels(channels)
    png = tonemap_rgb(rgb, exposure_stops=exposure_stops)
    Image.fromarray(png).save(path)


def export_crop(
    input_path: str | Path,
    output_dir: str | Path,
    region: Region,
    exposure_stops: float = 0.0,
    region_label: str | None = None,
) -> tuple[Path, Path]:
    image = read_exr(input_path)
    cropped = crop_channels(image.channels, region, image.width, image.height)

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    region_part = region.suffix() if region_label is None else f"{region_label}_{region.suffix()}"
    stem = f"{image.path.stem}_{region_part}"
    exr_path = output_path / f"{stem}.exr"
    png_path = output_path / f"{stem}.png"

    write_exr(exr_path, cropped, image.header)
    save_png(png_path, cropped, exposure_stops=exposure_stops)
    return exr_path, png_path


def save_reference_overlay(
    input_path: str | Path,
    output_dir: str | Path,
    region_boxes: list[tuple[Region, tuple[int, int, int], int]],
    exposure_stops: float = 0.0,
) -> Path:
    image = read_exr(input_path)
    if not region_boxes:
        raise ValueError("At least one region is required for the reference overlay.")

    rgb = rgb_from_channels(image.channels)
    png = tonemap_rgb(rgb, exposure_stops=exposure_stops)
    overlay = Image.fromarray(png)
    draw = ImageDraw.Draw(overlay)

    for region, box_color, line_width in region_boxes:
        region.validate(image.width, image.height)
        x0 = region.x
        y0 = region.y
        x1 = region.x + region.width - 1
        y1 = region.y + region.height - 1
        draw.rectangle((x0, y0, x1, y1), outline=box_color, width=max(1, int(line_width)))

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    overlay_path = output_path / f"{image.path.stem}_regions_overlay.png"
    overlay.save(overlay_path)
    return overlay_path
