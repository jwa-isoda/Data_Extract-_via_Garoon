#!/usr/bin/env python3
"""Extract 10 m U/V wind at multiple points from a supported GRIB2 message."""

from __future__ import annotations

import argparse
import csv
import math
import struct
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Sequence


def u16(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 2], "big")


def u32(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 4], "big")


def signed_magnitude(value: int, bits: int) -> int:
    sign = 1 << (bits - 1)
    return -(value & (sign - 1)) if value & sign else value


class BitReader:
    def __init__(self, data: memoryview):
        self.data = data
        self.index = 0
        self.accumulator = 0
        self.available = 0

    def read(self, width: int) -> int:
        if width == 0:
            return 0
        while self.available < width:
            if self.index >= len(self.data):
                raise EOFError("packed GRIB2 bitstream ended unexpectedly")
            self.accumulator = (self.accumulator << 8) | self.data[self.index]
            self.index += 1
            self.available += 8
        self.available -= width
        value = (self.accumulator >> self.available) & ((1 << width) - 1)
        self.accumulator &= (1 << self.available) - 1
        return value

    def align_byte(self) -> None:
        self.accumulator = 0
        self.available = 0


@dataclass(frozen=True)
class Station:
    name: str
    latitude: float
    longitude: float


@dataclass(frozen=True)
class Grid:
    ni: int
    nj: int
    lat1: float
    lon1: float
    di: float
    dj: float
    scan_mode: int

    def nearest(self, station: Station) -> tuple[int, float, float]:
        if self.scan_mode & 0x30:
            raise ValueError(
                f"unsupported GRIB2 scan mode 0x{self.scan_mode:02x}: "
                "adjacent-j or alternating-row layout"
            )
        i_step = -self.di if self.scan_mode & 0x80 else self.di
        j_step = self.dj if self.scan_mode & 0x40 else -self.dj
        i = round((station.longitude - self.lon1) / i_step)
        j = round((station.latitude - self.lat1) / j_step)
        if not (0 <= i < self.ni and 0 <= j < self.nj):
            raise ValueError(f"station {station.name!r} lies outside the GRIB2 grid")
        return j * self.ni + i, self.lat1 + j * j_step, self.lon1 + i * i_step


@dataclass(frozen=True)
class Field:
    category: int
    parameter: int
    surface_type: int
    surface_value: float
    section4: int
    section5: int
    bitmap_section: int | None
    section7: int


def validate_message(data: bytes) -> None:
    if len(data) < 20 or data[:4] != b"GRIB":
        raise ValueError("not a GRIB message")
    if data[7] != 2:
        raise ValueError(f"unsupported GRIB edition {data[7]}")
    declared = int.from_bytes(data[8:16], "big")
    if declared != len(data):
        raise ValueError(f"GRIB2 length mismatch: declared={declared}, actual={len(data)}")
    if data[-4:] != b"7777":
        raise ValueError("GRIB2 Section 8 terminator is missing")


def iter_sections(data: bytes) -> Iterable[tuple[int, int, int]]:
    position = 16
    while position < len(data) - 4:
        if position + 5 > len(data) - 4:
            raise ValueError("truncated GRIB2 section header")
        length = u32(data, position)
        if length < 5 or position + length > len(data) - 4:
            raise ValueError(f"invalid GRIB2 section length at offset {position}")
        yield data[position + 4], position, length
        position += length
    if position != len(data) - 4:
        raise ValueError("GRIB2 sections do not end at Section 8")


def parse_grid(data: bytes) -> Grid:
    for number, position, _ in iter_sections(data):
        if number != 3:
            continue
        template = u16(data, position + 12)
        if template != 0:
            raise ValueError(f"unsupported Grid Definition Template 3.{template}")
        ni, nj = u32(data, position + 30), u32(data, position + 34)
        lat1 = signed_magnitude(u32(data, position + 46), 32) / 1_000_000.0
        lon1 = signed_magnitude(u32(data, position + 50), 32) / 1_000_000.0
        di = u32(data, position + 63) / 1_000_000.0
        dj = u32(data, position + 67) / 1_000_000.0
        if not ni or not nj or not di or not dj:
            raise ValueError("invalid regular latitude/longitude grid")
        return Grid(ni, nj, lat1, lon1, di, dj, data[position + 71])
    raise ValueError("GRIB2 Section 3 was not found")


def scaled_surface(data: bytes, section4: int) -> float:
    scale = signed_magnitude(data[section4 + 23], 8)
    return u32(data, section4 + 24) * 10.0 ** (-scale)


def find_fields(data: bytes) -> list[Field]:
    fields: list[Field] = []
    current: dict[str, int | None] = {}
    last_bitmap: int | None = None
    for section, position, _ in iter_sections(data):
        if section == 4:
            current = {"section4": position}
        elif section == 5:
            current["section5"] = position
        elif section == 6:
            indicator = data[position + 5]
            if indicator == 0:
                last_bitmap = position
                current["bitmap_section"] = position
            elif indicator == 254:
                if last_bitmap is None:
                    raise ValueError("bitmap reuse requested before a bitmap was defined")
                current["bitmap_section"] = last_bitmap
            elif indicator == 255:
                current["bitmap_section"] = None
            else:
                raise ValueError(f"unsupported bitmap indicator {indicator}")
        elif section == 7:
            required = {"section4", "section5", "bitmap_section"}
            if not required.issubset(current):
                raise ValueError("incomplete GRIB2 field before Section 7")
            s4 = int(current["section4"])
            fields.append(
                Field(
                    category=data[s4 + 9],
                    parameter=data[s4 + 10],
                    surface_type=data[s4 + 22],
                    surface_value=scaled_surface(data, s4),
                    section4=s4,
                    section5=int(current["section5"]),
                    bitmap_section=current["bitmap_section"],
                    section7=position,
                )
            )
    return fields


def packed_index(data: bytes, bitmap_section: int | None, grid_index: int) -> int:
    if bitmap_section is None:
        return grid_index
    bitmap = memoryview(data)[
        bitmap_section + 6 : bitmap_section + u32(data, bitmap_section)
    ]
    byte_index, bit_offset = divmod(grid_index, 8)
    if byte_index >= len(bitmap):
        raise IndexError("grid index exceeds Section 6 bitmap")
    if not ((bitmap[byte_index] >> (7 - bit_offset)) & 1):
        raise ValueError("requested grid point is missing according to Section 6")
    before = sum(byte.bit_count() for byte in bitmap[:byte_index])
    if bit_offset:
        before += (bitmap[byte_index] >> (8 - bit_offset)).bit_count()
    return before


def _scale_value(reference: float, binary: int, decimal: int, value: int) -> float:
    return (reference + value * 2.0**binary) / 10.0**decimal


def _decode_simple(data: bytes, field: Field, targets: set[int]) -> dict[int, float]:
    s5, s7 = field.section5, field.section7
    reference = struct.unpack(">f", data[s5 + 11 : s5 + 15])[0]
    binary = signed_magnitude(u16(data, s5 + 15), 16)
    decimal = signed_magnitude(u16(data, s5 + 17), 16)
    width = data[s5 + 19]
    payload = memoryview(data)[s7 + 5 : s7 + u32(data, s7)]
    result: dict[int, float] = {}
    for target in targets:
        bit = target * width
        reader = BitReader(payload[bit // 8 :])
        if bit % 8:
            reader.read(bit % 8)
        raw = reader.read(width)
        result[target] = _scale_value(reference, binary, decimal, raw)
    return result


def _decode_complex(data: bytes, field: Field, targets: set[int]) -> dict[int, float]:
    s5, s7 = field.section5, field.section7
    reference = struct.unpack(">f", data[s5 + 11 : s5 + 15])[0]
    binary = signed_magnitude(u16(data, s5 + 15), 16)
    decimal = signed_magnitude(u16(data, s5 + 17), 16)
    reference_bits = data[s5 + 19]
    missing_management = data[s5 + 22]
    number_groups = u32(data, s5 + 31)
    reference_width = data[s5 + 35]
    width_bits = data[s5 + 36]
    reference_length = u32(data, s5 + 37)
    length_increment = data[s5 + 41]
    last_length = u32(data, s5 + 42)
    length_bits = data[s5 + 46]
    order = data[s5 + 47]
    descriptor_octets = data[s5 + 48]
    if missing_management != 0:
        raise ValueError("Template 5.3 missing-value management is unsupported")
    if order not in (1, 2):
        raise ValueError(f"unsupported spatial differencing order {order}")

    payload_start = s7 + 5
    descriptor_count = order + 1
    descriptors: list[int] = []
    for index in range(descriptor_count):
        begin = payload_start + index * descriptor_octets
        raw = int.from_bytes(data[begin : begin + descriptor_octets], "big")
        descriptors.append(
            signed_magnitude(raw, descriptor_octets * 8)
            if index == order
            else raw
        )
    initial = descriptors[:order]
    minimum_difference = descriptors[-1]
    reader = BitReader(
        memoryview(data)[
            payload_start + descriptor_count * descriptor_octets : s7 + u32(data, s7)
        ]
    )
    references = [reader.read(reference_bits) for _ in range(number_groups)]
    reader.align_byte()
    widths = [reference_width + reader.read(width_bits) for _ in range(number_groups)]
    reader.align_byte()
    lengths = [
        reference_length + reader.read(length_bits) * length_increment
        for _ in range(number_groups)
    ]
    lengths[-1] = last_length
    reader.align_byte()

    result: dict[int, float] = {}
    previous2, previous1 = initial[0], initial[-1]
    sequence_index = 0
    for group_reference, width, length in zip(references, widths, lengths):
        for _ in range(length):
            packed = group_reference + reader.read(width)
            if sequence_index < order:
                value = initial[sequence_index]
            else:
                residual = packed + minimum_difference
                if order == 1:
                    value = previous1 + residual
                    previous1 = value
                else:
                    value = 2 * previous1 - previous2 + residual
                    previous2, previous1 = previous1, value
            if sequence_index in targets:
                result[sequence_index] = _scale_value(
                    reference, binary, decimal, value
                )
                if len(result) == len(targets):
                    return result
            sequence_index += 1
    missing = sorted(targets - result.keys())
    raise IndexError(f"packed indexes were not decoded: {missing[:5]}")


def decode_values(data: bytes, field: Field, indexes: Sequence[int]) -> dict[int, float]:
    targets = set(indexes)
    template = u16(data, field.section5 + 9)
    if template == 0:
        return _decode_simple(data, field, targets)
    if template == 3:
        return _decode_complex(data, field, targets)
    raise ValueError(f"unsupported Data Representation Template 5.{template}")


def reference_time(data: bytes) -> datetime:
    for number, position, _ in iter_sections(data):
        if number == 1:
            return datetime(
                u16(data, position + 12),
                data[position + 14],
                data[position + 15],
                data[position + 16],
                data[position + 17],
                data[position + 18],
                tzinfo=timezone.utc,
            )
    raise ValueError("GRIB2 Section 1 was not found")


def valid_time(data: bytes, field: Field) -> datetime:
    unit = data[field.section4 + 17]
    lead = u32(data, field.section4 + 18)
    seconds_per_unit = {
        0: 60,
        1: 3600,
        2: 86400,
        10: 10800,
        11: 21600,
        12: 43200,
        13: 1,
    }
    if unit not in seconds_per_unit:
        raise ValueError(f"unsupported GRIB2 forecast-time unit {unit}")
    return reference_time(data) + timedelta(seconds=lead * seconds_per_unit[unit])


def extract_uv(
    data: bytes,
    stations: Sequence[Station],
    *,
    surface_type: int = 103,
    surface_value: float = 10.0,
) -> tuple[datetime, list[dict[str, object]]]:
    validate_message(data)
    grid = parse_grid(data)
    fields = find_fields(data)
    selected = {
        field.parameter: field
        for field in fields
        if field.category == 2
        and field.parameter in (2, 3)
        and field.surface_type == surface_type
        and math.isclose(field.surface_value, surface_value)
    }
    if set(selected) != {2, 3}:
        raise ValueError("requested U/V wind fields were not found")

    locations = [grid.nearest(station) for station in stations]
    packed_by_parameter: dict[int, list[int]] = {}
    decoded_by_parameter: dict[int, dict[int, float]] = {}
    for parameter in (2, 3):
        field = selected[parameter]
        packed = [packed_index(data, field.bitmap_section, item[0]) for item in locations]
        packed_by_parameter[parameter] = packed
        decoded_by_parameter[parameter] = decode_values(data, field, packed)

    rows: list[dict[str, object]] = []
    for index, (station, (_, grid_lat, grid_lon)) in enumerate(zip(stations, locations)):
        u = decoded_by_parameter[2][packed_by_parameter[2][index]]
        v = decoded_by_parameter[3][packed_by_parameter[3][index]]
        mean_lat = math.radians((station.latitude + grid_lat) / 2)
        north_km = (grid_lat - station.latitude) * 111.32
        east_km = (grid_lon - station.longitude) * 111.32 * math.cos(mean_lat)
        rows.append(
            {
                "station": station.name,
                "station_latitude": station.latitude,
                "station_longitude": station.longitude,
                "grid_latitude": grid_lat,
                "grid_longitude": grid_lon,
                "grid_distance_km": math.hypot(north_km, east_km),
                "u_mps": u,
                "v_mps": v,
                "wind_speed_mps": math.hypot(u, v),
            }
        )
    return valid_time(data, selected[2]), rows


def read_stations(path: Path | None, inline: Sequence[str]) -> list[Station]:
    stations: list[Station] = []
    if path:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                stations.append(
                    Station(row["name"], float(row["latitude"]), float(row["longitude"]))
                )
    for item in inline:
        try:
            name, latitude, longitude = item.split(",", 2)
        except ValueError as error:
            raise ValueError("--station must be NAME,LATITUDE,LONGITUDE") from error
        stations.append(Station(name, float(latitude), float(longitude)))
    if not stations:
        raise ValueError("provide --stations-csv or at least one --station")
    return stations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("grib2", type=Path)
    parser.add_argument("--stations-csv", type=Path)
    parser.add_argument("--station", action="append", default=[])
    parser.add_argument("--surface-type", type=int, default=103)
    parser.add_argument("--surface-value", type=float, default=10.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    stations = read_stations(args.stations_csv, args.station)
    timestamp, rows = extract_uv(
        args.grib2.read_bytes(),
        stations,
        surface_type=args.surface_type,
        surface_value=args.surface_value,
    )
    fieldnames = ["valid_time_utc", "source_file", *rows[0].keys()]
    output = args.output or args.grib2.with_suffix(".wind.csv")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "valid_time_utc": timestamp.isoformat(),
                    "source_file": args.grib2.name,
                    **row,
                }
            )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
