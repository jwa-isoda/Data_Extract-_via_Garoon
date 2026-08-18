# Validation checklist

## Time and row counts

- Generate the expected timestamp set before collection.
- For a complete UTC day expect 24 hourly or 48 half-hourly timestamps per station.
- Treat inclusive end times carefully; calculate expected counts programmatically.
- Compare expected keys with actual keys and report missing, extra, and duplicate rows.
- Pair products by `(valid_time, station)`, never by row number.

## Grid checks

- Record station and selected-grid latitude/longitude.
- Calculate and inspect approximate station-to-grid distance.
- Verify that the station lies inside the grid.
- Recheck scan mode and grid index calculation for each new product/grid.

## Field checks

- Confirm Edition 2, parameter metadata, vertical surface, representation template, and bitmap indicator.
- Confirm both U and V exist for each accepted message.
- Reject unsupported templates rather than returning guessed values.
- Check that values are finite and in m/s.
- Compare at least one timestamp/site with ecCodes or another trusted decoder for each new product version.

## Comparison checks

- Confirm x is the reference product and y is the comparison product.
- Calculate error as `comparison - reference` and label it explicitly.
- Use the exact same paired rows for regression, correlation, RMSE, MAE, bias, and plots.
- Give each component plot identical x/y limits so the `x = y` line is visually meaningful.
- Confirm the statistics CSV row count equals the plotted sample count.

## Delivery checks

- State the period, interval, timezone, products, station coordinates, nearest-grid coordinates, software command, and missing data.
- Keep reusable code separate from generated CSV, SVG/PNG, logs, caches, and downloaded GRIB files.
- Scan publishable files for credentials, internal URLs, usernames, and absolute local paths.
