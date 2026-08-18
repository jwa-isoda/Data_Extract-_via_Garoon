#!/usr/bin/env python3
"""Stream a remote tar.bz2 over FTP and extract GRIB2 U/V rows without unpacking to disk."""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
import tarfile
from ftplib import FTP
from pathlib import Path

from grib2_wind import extract_uv, read_stations


OUTPUT_COLUMNS = [
    "valid_time_utc",
    "source_archive",
    "member",
    "station",
    "station_latitude",
    "station_longitude",
    "grid_latitude",
    "grid_longitude",
    "grid_distance_km",
    "u_mps",
    "v_mps",
    "wind_speed_mps",
]


def process_archive(args: argparse.Namespace) -> tuple[int, int]:
    stations = read_stations(args.stations_csv, args.station)
    member_pattern = re.compile(args.member_regex)
    password = os.environ.get(args.password_env, "anonymous@")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    accepted = 0
    rejected = 0

    ftp = FTP(timeout=args.timeout)
    try:
        ftp.connect(args.host, args.port)
        ftp.login(args.user, password)
        ftp.set_pasv(not args.active)
        data_socket = ftp.transfercmd(f"RETR {args.remote_archive}")
        try:
            with data_socket.makefile("rb") as ftp_stream, args.output.open(
                "w", encoding="utf-8-sig", newline=""
            ) as output_handle:
                writer = csv.DictWriter(output_handle, fieldnames=OUTPUT_COLUMNS)
                writer.writeheader()
                with tarfile.open(fileobj=ftp_stream, mode="r|bz2") as archive:
                    for member in archive:
                        if not member.isfile() or not member_pattern.search(member.name):
                            continue
                        source = archive.extractfile(member)
                        if source is None:
                            continue
                        try:
                            with source:
                                data = source.read()
                            timestamp, rows = extract_uv(
                                data,
                                stations,
                                surface_type=args.surface_type,
                                surface_value=args.surface_value,
                            )
                        except Exception as error:
                            rejected += 1
                            print(f"SKIP {member.name}: {error}", file=sys.stderr)
                            if args.strict:
                                raise
                            continue
                        for row in rows:
                            writer.writerow(
                                {
                                    "valid_time_utc": timestamp.isoformat(),
                                    "source_archive": args.remote_archive,
                                    "member": member.name,
                                    **row,
                                }
                            )
                        output_handle.flush()
                        accepted += 1
                        print(f"OK {member.name}", file=sys.stderr)
        finally:
            data_socket.close()
        ftp.voidresp()
    finally:
        try:
            ftp.quit()
        except Exception:
            ftp.close()
    return accepted, rejected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host", help="FTP server hostname or IP address")
    parser.add_argument("remote_archive", help="absolute remote .tar.bz2 path")
    parser.add_argument("output", type=Path)
    parser.add_argument("--port", type=int, default=21)
    parser.add_argument("--user", default="anonymous")
    parser.add_argument(
        "--password-env",
        default="WIND_FTP_PASSWORD",
        help="environment variable holding the FTP password",
    )
    parser.add_argument("--stations-csv", type=Path)
    parser.add_argument("--station", action="append", default=[])
    parser.add_argument("--surface-type", type=int, default=103)
    parser.add_argument("--surface-value", type=float, default=10.0)
    parser.add_argument("--member-regex", default=r"(?i)\.(?:bin|grb|grib|grib2)$")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--active", action="store_true", help="disable passive FTP")
    parser.add_argument("--strict", action="store_true", help="stop on first rejected member")
    args = parser.parse_args()

    accepted, rejected = process_archive(args)
    print(f"accepted_members={accepted} rejected_members={rejected}")
    if accepted == 0:
        raise SystemExit("no GRIB2 members were accepted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
