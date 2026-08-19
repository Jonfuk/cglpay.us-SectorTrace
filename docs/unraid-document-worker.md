# Unraid document-analysis worker

Run document analysis in this dedicated Docker image on Unraid. It contains
the Python document dependencies plus the operating-system OCR binaries
Tesseract and Ghostscript. The ordinary `Dockerfile` remains the lightweight
Railway/web image and should not be used for OCR batches.

The checkout also includes `deploy/unraid-document-worker.sh`, a wrapper that
keeps the image name, environment-file location, user mapping, and local data
mount consistent. Use it from the checkout:

```bash
chmod +x deploy/unraid-document-worker.sh
./deploy/unraid-document-worker.sh build
./deploy/unraid-document-worker.sh verify
./deploy/unraid-document-worker.sh status
```

## Build

From the repository checkout on Unraid:

```bash
cd /mnt/user/Data/cglpay.us-SectorTrace
git pull origin master
docker build -f deploy/Dockerfile.documents -t sectortrace-document-worker:latest .
```

The same build through the wrapper is:

```bash
./deploy/unraid-document-worker.sh build
```

Rebuild after pulling a new application commit or lockfile. No secrets are
copied into the image.

## Configuration and storage

Place an environment file with the existing `DATABASE_URL`, archive, derived
S3, and document-analysis settings somewhere persistent, for example:

```bash
mkdir -p /mnt/user/appdata/sectortrace
cp .env /mnt/user/appdata/sectortrace/document-worker.env
chmod 600 /mnt/user/appdata/sectortrace/document-worker.env
```

Use the configured S3 archive when possible. If `RAW_ARCHIVE_DIR` or
`DERIVED_ARCHIVE_DIR` points to local storage, bind-mount the checkout's
`data` directory at `/app/data`; otherwise raw objects or local artifacts will
not be visible in the container.

## Verify the worker

For an S3-backed raw and derived archive:

```bash
docker run --rm --user 99:100 \
  --env-file /mnt/user/appdata/sectortrace/document-worker.env \
  sectortrace-document-worker:latest documents status
```

Or use:

```bash
./deploy/unraid-document-worker.sh status
```

For a filesystem-backed archive, add this volume to every worker command:

```bash
-v /mnt/user/Data/cglpay.us-SectorTrace/data:/app/data
```

Then verify the required binaries:

```bash
docker run --rm --entrypoint /bin/sh sectortrace-document-worker:latest \
  -c 'tesseract --version && gs --version && ocrmypdf --version'
```

The wrapper equivalent is `./deploy/unraid-document-worker.sh verify`.

## Run a batch

The worker's entry point is `pipeline`, so run individual commands directly:

```bash
docker run --rm --user 99:100 \
  --env-file /mnt/user/appdata/sectortrace/document-worker.env \
  sectortrace-document-worker:latest documents validate
```

For any other pipeline command, use:

```bash
./deploy/unraid-document-worker.sh command documents stats
./deploy/unraid-document-worker.sh validate
```

For the long-running batch script, create a copy that omits its host-only
`git pull` and `uv sync` lines; the image is rebuilt to update its code and
dependencies. Mount that script and override the entry point:

```bash
docker run --rm --name sectortrace-document-batch --user 99:100 \
  --env-file /mnt/user/appdata/sectortrace/document-worker.env \
  -v /mnt/user/Data/cglpay.us-SectorTrace/batch.container.sh:/work/batch.sh:ro \
  --entrypoint /bin/bash \
  sectortrace-document-worker:latest /work/batch.sh
```

With the wrapper:

```bash
./deploy/unraid-document-worker.sh batch /path/to/batch.container.sh
```

Add the `data` volume above to that command if the raw or derived archive is
filesystem-backed. The worker writes only PostgreSQL and the configured
archive destinations; it does not alter the Unraid host's package set.
