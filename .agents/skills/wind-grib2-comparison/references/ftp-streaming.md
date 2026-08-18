# FTP tar.bz2 streaming

## Data flow

Process an archive as:

```text
FTP control session
  -> RETR data connection
  -> compressed byte stream
  -> incremental bz2 decompressor
  -> sequential tar member reader
  -> one GRIB2 member in memory
  -> all station values
  -> CSV rows
```

Use `FTP.transfercmd("RETR ...")` to obtain the data socket and `tarfile.open(fileobj=stream, mode="r|bz2")` for sequential expansion. `TarFile.extractfile()` returns a readable member stream; it does not create a local file. Avoid `extract()` and `extractall()` when diskless operation is required.

The compressed archive and expanded tar are not saved by this pattern. One GRIB member is read into RAM because the bundled GRIB decoder needs random byte access within that message. Results are appended to the output CSV.

## Operational constraints

- bzip2/tar streaming is sequential; reaching a late member requires reading earlier compressed data.
- A broken FTP transfer normally requires restarting that daily archive unless a verified restart strategy exists.
- Use passive FTP unless the network requires active mode.
- Plain FTP is unencrypted. Use it only on an approved network and never embed credentials.
- Keep concurrency within server connection limits; parallelize by daily archive, not by member within one stream.
- Close the member stream, tar reader, data socket, and FTP control session on errors.
- Call `voidresp()` after the data connection closes so the final FTP transfer status is consumed.

## Publishing code

Replace internal hostnames and paths with CLI parameters. Read non-anonymous passwords from an environment variable. Do not include cookies, captured browser profiles, downloaded data, or operational server details in a public repository.
