# GRIB2 wind comparison

Apply a reproducible workflow for extracting and comparing 10 m U/V winds. Keep acquisition, decoding, pairing, statistics, plotting, and validation as separate stages.

## Establish the run contract

Confirm or infer these inputs before a long run:

- product names and source locations;
- UTC/JST interpretation and requested output timezone;
- start/end timestamps and hourly or 30-minute interval;
- station names and coordinates;
- surface selector, normally type 103 at 10 m;
- output directory and required plots/statistics.

Do not assume `FLA` is a universally recognized expansion. Treat it as a configured product label and record the underlying product identifier in the run documentation.

## Choose the acquisition path

- For local `.bin`, `.grb`, `.grib2`, or `.grib` files, use `scripts/grib2_wind.py` or adapt its decoder.
- For FTP-hosted `.tar.bz2` archives, read `references/ftp-streaming.md`, then use `scripts/stream_ftp_tar_uv.py` as the starting point.
- For authenticated browser proxy sources, reuse project-specific acquisition code only after separating cookies, credentials, hostnames, and absolute paths from publishable code.

Never commit passwords, session cookies, tokens, internal hostnames, private URLs, or user-specific absolute paths. Pass them at runtime or through environment variables.

## Decode and extract

Read `references/grib2-wind-fields.md` before changing GRIB2 parsing or supporting a new product.

1. Validate `GRIB`, Edition 2, declared message length, and the `7777` terminator when the complete message is available.
2. Parse Section 3 and calculate one nearest-grid index per station.
3. Scan repeated Sections 4-7; never rely on a fixed field order.
4. Select U with category 2/parameter 2 and V with category 2/parameter 3.
5. Require the requested vertical surface; default to type 103/value 10 for 10 m wind.
6. Apply Section 6 bitmap mapping before decoding Section 7.
7. Decode template 5.0 or 5.3 according to Section 5.
8. Extract all requested stations from each GRIB message before discarding it.
9. Compute speed with `math.hypot(u, v)`; retain signed U and V unchanged.

Test a new product against ecCodes or a trusted sample before processing a year. A matching filename or `GRIB` header alone does not prove that the decoder supports its templates.

## Pair products

Create one row per common valid time and station. Keep unmatched source rows in diagnostics instead of silently pairing by row position.

Use explicit columns such as:

```text
time,station,FLA_U_mps,FLA_V_mps,LFM_U_mps,LFM_V_mps
```

Record valid time rather than only file creation or reference time. Convert timezone exactly once and state it in both the column name and run documentation.

## Analyze U and V separately

Use `scripts/compare_uv.py` for a paired CSV or reproduce the same definitions:

- x-axis: first/reference product, normally FLA;
- y-axis: second/comparison product, normally LFM;
- add dashed `x = y` and a linear regression line;
- use identical x/y limits within each component plot;
- write slope, intercept, Pearson correlation, RMSE, MAE, and mean error `comparison - reference` to CSV.

Do not force U and V to share the same range unless requested. Honor explicit limits such as a V-axis minimum of -15 m/s.

## Validate before reporting completion

Read `references/validation.md` and verify at minimum:

- expected timestamps versus extracted timestamps;
- duplicate and missing key counts;
- nearest-grid coordinates and distances;
- finite U/V values and plausible units;
- paired row count used by both CSV statistics and plots;
- regression orientation and error sign;
- output filenames, timezone labels, and period boundaries.

Write a short run README in the result directory when the user requests a deliverable folder. Describe source products, coordinates, time basis, commands, outputs, missing data, and validation. Do not add a README inside this Skill itself.

## Bundled resources

- `scripts/grib2_wind.py`: dependency-free decoder and multi-station extractor for the supported regular lat/lon GRIB2 subset.
- `scripts/stream_ftp_tar_uv.py`: sequential FTP -> bz2 -> tar -> GRIB2 processing without archive extraction to disk.
- `scripts/compare_uv.py`: paired U/V regression statistics and SVG scatterplots.
- `assets/stations.example.csv`: station input template.
- `references/grib2-wind-fields.md`: field selectors, templates, and decoding assumptions.
- `references/ftp-streaming.md`: FTP stream behavior and operational cautions.
- `references/validation.md`: count, time, grid, and statistical checks.
