#!/usr/bin/env python3
"""Compare paired U/V columns, write regression statistics, and draw SVG scatterplots."""

from __future__ import annotations

import argparse
import csv
import html
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


@dataclass(frozen=True)
class Stats:
    count: int
    slope: float
    intercept: float
    correlation: float
    rmse: float
    mae: float
    bias: float


def calculate(x: Sequence[float], y: Sequence[float]) -> Stats:
    if len(x) != len(y) or len(x) < 2:
        raise ValueError("each component requires at least two paired values")
    count = len(x)
    mean_x = sum(x) / count
    mean_y = sum(y) / count
    sxx = sum((value - mean_x) ** 2 for value in x)
    syy = sum((value - mean_y) ** 2 for value in y)
    sxy = sum((a - mean_x) * (b - mean_y) for a, b in zip(x, y))
    if sxx == 0 or syy == 0:
        raise ValueError("regression/correlation is undefined for a constant component")
    errors = [b - a for a, b in zip(x, y)]
    return Stats(
        count=count,
        slope=sxy / sxx,
        intercept=mean_y - (sxy / sxx) * mean_x,
        correlation=sxy / math.sqrt(sxx * syy),
        rmse=math.sqrt(sum(error * error for error in errors) / count),
        mae=sum(abs(error) for error in errors) / count,
        bias=sum(errors) / count,
    )


def load_pairs(path: Path, x_column: str, y_column: str) -> tuple[list[float], list[float]]:
    x: list[float] = []
    y: list[float] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or x_column not in reader.fieldnames or y_column not in reader.fieldnames:
            raise ValueError(f"missing columns {x_column!r} and/or {y_column!r}")
        for number, row in enumerate(reader, start=2):
            if not row[x_column] or not row[y_column]:
                continue
            try:
                a, b = float(row[x_column]), float(row[y_column])
            except ValueError as error:
                raise ValueError(f"non-numeric value at CSV row {number}") from error
            if math.isfinite(a) and math.isfinite(b):
                x.append(a)
                y.append(b)
    return x, y


def choose_limits(
    x: Sequence[float],
    y: Sequence[float],
    requested_min: float | None,
    requested_max: float | None,
) -> tuple[float, float]:
    low = min(min(x), min(y)) if requested_min is None else requested_min
    high = max(max(x), max(y)) if requested_max is None else requested_max
    if requested_min is None or requested_max is None:
        padding = max((high - low) * 0.05, 0.5)
        if requested_min is None:
            low -= padding
        if requested_max is None:
            high += padding
    if not low < high:
        raise ValueError("axis minimum must be less than axis maximum")
    return low, high


def write_svg(
    path: Path,
    component: str,
    x: Sequence[float],
    y: Sequence[float],
    stats: Stats,
    limits: tuple[float, float],
    x_label: str,
    y_label: str,
) -> None:
    width, height = 760, 720
    left, right, top, bottom = 90, 30, 55, 85
    plot_w, plot_h = width - left - right, height - top - bottom
    low, high = limits

    def px(value: float) -> float:
        return left + (value - low) / (high - low) * plot_w

    def py(value: float) -> float:
        return top + (high - value) / (high - low) * plot_h

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{width/2}" y="28" text-anchor="middle" font-family="sans-serif" font-size="20">{html.escape(component)} wind comparison</text>',
        f'<rect x="{left}" y="{top}" width="{plot_w}" height="{plot_h}" fill="none" stroke="#222"/>',
    ]
    for tick_index in range(9):
        value = low + (high - low) * tick_index / 8
        x_pos, y_pos = px(value), py(value)
        parts.extend(
            [
                f'<line x1="{x_pos:.2f}" y1="{top}" x2="{x_pos:.2f}" y2="{top+plot_h}" stroke="#ddd"/>',
                f'<line x1="{left}" y1="{y_pos:.2f}" x2="{left+plot_w}" y2="{y_pos:.2f}" stroke="#ddd"/>',
                f'<text x="{x_pos:.2f}" y="{top+plot_h+24}" text-anchor="middle" font-family="sans-serif" font-size="12">{value:.1f}</text>',
                f'<text x="{left-10}" y="{y_pos+4:.2f}" text-anchor="end" font-family="sans-serif" font-size="12">{value:.1f}</text>',
            ]
        )
    parts.append(
        f'<line x1="{px(low):.2f}" y1="{py(low):.2f}" x2="{px(high):.2f}" y2="{py(high):.2f}" stroke="#555" stroke-width="2" stroke-dasharray="8 7"/>'
    )
    reg_y0 = stats.slope * low + stats.intercept
    reg_y1 = stats.slope * high + stats.intercept
    parts.append(
        f'<line x1="{px(low):.2f}" y1="{py(reg_y0):.2f}" x2="{px(high):.2f}" y2="{py(reg_y1):.2f}" stroke="#d62728" stroke-width="2" clip-path="url(#clip)"/>'
    )
    parts.insert(
        2,
        f'<defs><clipPath id="clip"><rect x="{left}" y="{top}" width="{plot_w}" height="{plot_h}"/></clipPath></defs>',
    )
    for a, b in zip(x, y):
        parts.append(
            f'<circle cx="{px(a):.2f}" cy="{py(b):.2f}" r="2.1" fill="#1f77b4" fill-opacity="0.35" clip-path="url(#clip)"/>'
        )
    parts.extend(
        [
            f'<text x="{left+plot_w/2}" y="{height-25}" text-anchor="middle" font-family="sans-serif" font-size="15">{html.escape(x_label)}</text>',
            f'<text x="22" y="{top+plot_h/2}" text-anchor="middle" font-family="sans-serif" font-size="15" transform="rotate(-90 22 {top+plot_h/2})">{html.escape(y_label)}</text>',
            f'<text x="{left+12}" y="{top+24}" font-family="sans-serif" font-size="13">y = {stats.slope:.6f} x {stats.intercept:+.6f}</text>',
            f'<text x="{left+12}" y="{top+44}" font-family="sans-serif" font-size="13">r = {stats.correlation:.6f}, n = {stats.count}</text>',
            '</svg>',
        ]
    )
    path.write_text("\n".join(parts), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("--x-product", default="FLA")
    parser.add_argument("--y-product", default="LFM")
    parser.add_argument("--x-u-column", default="FLAの東西風")
    parser.add_argument("--x-v-column", default="FLAの南北風")
    parser.add_argument("--y-u-column", default="LFMの東西風")
    parser.add_argument("--y-v-column", default="LFMの南北風")
    parser.add_argument("--u-min", type=float)
    parser.add_argument("--u-max", type=float)
    parser.add_argument("--v-min", type=float)
    parser.add_argument("--v-max", type=float)
    args = parser.parse_args()

    args.output_directory.mkdir(parents=True, exist_ok=True)
    definitions = {
        "U": (args.x_u_column, args.y_u_column, args.u_min, args.u_max),
        "V": (args.x_v_column, args.y_v_column, args.v_min, args.v_max),
    }
    results: dict[str, Stats] = {}
    for component, (x_column, y_column, axis_min, axis_max) in definitions.items():
        x, y = load_pairs(args.input, x_column, y_column)
        stats = calculate(x, y)
        results[component] = stats
        limits = choose_limits(x, y, axis_min, axis_max)
        write_svg(
            args.output_directory / f"{component}_scatter_regression.svg",
            component,
            x,
            y,
            stats,
            limits,
            f"{args.x_product} {component} (m/s)",
            f"{args.y_product} {component} (m/s)",
        )

    statistics_path = args.output_directory / "UV_regression_statistics.csv"
    with statistics_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "component",
                "count",
                "regression_equation",
                "slope",
                "intercept_mps",
                "correlation",
                "RMSE_mps",
                "MAE_mps",
                f"mean_error_{args.y_product}_minus_{args.x_product}_mps",
            ]
        )
        for component in ("U", "V"):
            value = results[component]
            writer.writerow(
                [
                    component,
                    value.count,
                    f"{args.y_product} = {value.slope:.6f} * {args.x_product} {value.intercept:+.6f}",
                    f"{value.slope:.6f}",
                    f"{value.intercept:.6f}",
                    f"{value.correlation:.6f}",
                    f"{value.rmse:.6f}",
                    f"{value.mae:.6f}",
                    f"{value.bias:.6f}",
                ]
            )
    print(statistics_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
