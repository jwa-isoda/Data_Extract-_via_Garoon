# GRIB2 wind fields

## Supported subset

The bundled decoder targets GRIB2 Edition 2 messages on regular latitude/longitude grids using Grid Definition Template 3.0. It supports:

- Data Representation Template 5.0: simple packing;
- Data Representation Template 5.3: complex packing with spatial differencing;
- Section 6 bitmap indicators 0 (included), 254 (reuse), and 255 (no bitmap);
- scan modes with adjacent points in the i direction and no alternating rows.

Treat any other grid, scan pattern, bitmap mode, missing-value management, or data-representation template as unsupported until tested.

## Wind selectors

For the products used in this workflow:

| Quantity | Discipline | Category | Parameter |
|---|---:|---:|---:|
| U component | 0 | 2 | 2 |
| V component | 0 | 2 | 3 |

The usual 10 m selector is fixed height above ground, surface type 103, scaled value 10 m. Verify the Product Definition Template and local product documentation before applying this selector to a new dataset.

U is positive eastward and V is positive northward. Calculate scalar wind speed as `sqrt(U^2 + V^2)` or `math.hypot(U, V)`.

## Sections used

- Section 0: marker, discipline, edition, total message length.
- Section 1: reference time.
- Section 3: grid dimensions, first point, increments, and scan mode.
- Section 4: parameter, surface, and forecast-time metadata.
- Section 5: packing template and scale factors.
- Section 6: bitmap and bitmap reuse.
- Section 7: packed values.
- Section 8: `7777` terminator.

Sections 4-7 repeat for each field. Search all fields and select by metadata; do not assume U and V are the first two fields unless the product contract explicitly guarantees it.

## Scaling

For simple and complex packing, recover a physical value from integer `X` using:

```text
Y = (R + X * 2^E) / 10^D
```

where `R` is the reference value, `E` the binary scale factor, and `D` the decimal scale factor.

Template 5.3 additionally requires group references, widths, lengths, and first- or second-order spatial-difference reconstruction. Bitmap mapping must occur before selecting the packed sequence index.

## Valid time

Distinguish:

- reference time from Section 1;
- forecast lead/unit from Section 4;
- valid time = reference time + forecast lead.

Analysis fields normally have zero lead, but verify rather than assume. Keep internal calculations timezone-aware in UTC and convert to JST only at the output boundary.
