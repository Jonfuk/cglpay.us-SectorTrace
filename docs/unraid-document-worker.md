# Unraid document-analysis worker

Run document and admin analysis in this dedicated Docker image on Unraid. It contains
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
copied into the image. The worker uses Debian Trixie so its Ghostscript is
newer than 10.02.0; OCRmyPDF rejects the 10.0.0–10.02.0 releases because of
known PDF-corruption regressions. Rebuilding replaces the previous image; it
does not alter Unraid's host packages or the database.

The worker deliberately installs the lightweight `pymupdf` parser and
OCRmyPDF rather than the full Docling extra. The tracked batch defaults to
`pymupdf`; installing Docling would add PyTorch and CUDA libraries of several
gigabytes without benefiting that batch. Legacy binary `.doc` files
(`application/msword`) are parsed through the `antiword` system binary; PDF,
DOCX, PPTX and HTML have their own stdlib/pymupdf parsers. A raw object in
any other format is skipped with a recorded reason (`SKIPPED_UNSUPPORTED_FORMAT`)
rather than aborting the batch.

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

## Run the admin analysis worker

The admin analysis page writes queued runs to the shared PostgreSQL warehouse.
Run the same image as a persistent queue consumer so those runs are claimed and
processed:

```bash
docker compose -f docker-compose.documents.yml up -d analysis-worker
docker compose -f docker-compose.documents.yml logs -f analysis-worker
```

The worker updates `analysis_worker_heartbeats`, claims one run at a time,
processes document windows in resumable batches, records emerging themes, and
honours Stop/Resume from `/admin/analysis`. The `.env` used by the service must
point at the same `DATABASE_URL` as the web application.

For a filesystem-backed archive, add this volume to every worker command:

```bash
-v /mnt/user/Data/cglpay.us-SectorTrace/data:/app/data
```

Then verify the required binaries:

```bash
docker run --rm --entrypoint /bin/sh sectortrace-document-worker:latest \
  -c 'tesseract --version && gs --version && ocrmypdf --version && command -v antiword'
```

The wrapper equivalent is `./deploy/unraid-document-worker.sh verify`.
Confirm that `gs --version` reports **10.02.1 or newer** before resuming an
OCR batch.

## Project into Neo4j

The worker also includes the graph driver. Set the following in
`/mnt/user/appdata/sectortrace/document-worker.env` before using graph commands:

```dotenv
NEO4J_ENABLED=true
NEO4J_URI=bolt://host.docker.internal:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=replace-with-the-Neo4j-password
NEO4J_DATABASE=neo4j
```

`host.docker.internal` reaches a Neo4j service published on the Unraid host;
the wrapper maps it to Docker's host gateway. Start the local service from the
checkout if it is not already running:

```bash
NEO4J_PASSWORD='choose-a-local-secret' \
  docker compose -f deploy/docker-compose.graph.yml up -d
```

After rebuilding the worker image, seed and rebuild the disposable graph:

```bash
./deploy/unraid-document-worker.sh command graph status
./deploy/unraid-document-worker.sh command graph backfill
./deploy/unraid-document-worker.sh command graph rebuild --clear
./deploy/unraid-document-worker.sh command graph status
```

This projects the document evidence records (source URL, retrieval metadata,
hash, and archive path) into Neo4j. Parsed document text and elements remain
canonical PostgreSQL records; they are not automatically promoted to claims or
duplicated as graph nodes.

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
./deploy/unraid-document-worker.sh batch /path/to/batch.sh
```

To process every supported provenance-complete legacy source, use the tracked
batch script instead of a committee-paper-only copy:

```bash
./deploy/unraid-document-worker.sh batch deploy/document-batch-all.sh
```

It processes `committee_papers`, `cdp_documents`, and `annual_reports` in
turn, dynamically using the source-system value returned by registration. It
is resumable and stops a source with unrecoverable raw objects rather than
silently skipping them. Its initial catch-up pass is deliberately limited to
those three document tables, never unrelated graph evidence. Set
`DOCUMENT_BATCH_SIZE` or `DOCUMENT_PARSER` in the environment to override its
defaults of `25` and `pymupdf`.

The wrapper accepts the existing host `batch.sh`: it makes an in-container
temporary copy that omits host `git pull` and `uv sync` commands. The container
image itself is the immutable code/dependency environment, so update
it with `git pull` followed by `./deploy/unraid-document-worker.sh build`
before starting a batch. It also sets a writable `UV_CACHE_DIR` for Unraid's
normal `99:100` container user. The copy changes `uv run pipeline` and
`uv run python` to the already-installed `pipeline` and `python` executables,
so an active batch never tries to synchronise or install packages at runtime.
The worker sends operational log files to its writable `/tmp/sectortrace-logs`
directory by default; batch state and parsed content remain durable in
PostgreSQL and the configured archives.

Add the `data` volume above to that command if the raw or derived archive is
filesystem-backed. The worker writes only PostgreSQL and the configured
archive destinations; it does not alter the Unraid host's package set.
