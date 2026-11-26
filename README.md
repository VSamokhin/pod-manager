# POD Manager

A small self-hosted web app for managing artwork for a print-on-demand business.

- **Images**: upload raster (PNG, JPG, WebP, TIFF, GIF, BMP) and vector (SVG) files. PDF, AI, EPS and PSD are stored and downloadable, without preview.
- **Flags**: mark images as ★ interesting and as successful or unsuccessful. Add tags and notes. Filter and search.
- **Drops**: group images into drops. Each drop has a state (Future, Released, Parked by default, editable by admins) and an optional planned date. For each image in a drop, tick the goods to print it on.
- **Templates**: vector frames applied to an image: padding and background, border, frame and image corner rounding, rectangular outline or a shape-following die-cut outline (traced from transparency), cut line, and a title. Live preview while adjusting.
- **Print export**: PNG (with DPI metadata), PDF or SVG, sized natively or to a goods type's print area. Renders can be saved back as new images linked to their original.
- **Admin**: drop states, goods types (with print area in mm), templates, and users with `admin` or `user` roles. Password login.

Stack: Python 3.13, FastAPI, Jinja2 templates, SQLite, Pillow, CairoSVG, NumPy. One container, no external services.

## Run the published image

Images are published to GHCR on GitHub-hosted runners and signed with cosign (keyless):

| Tag | Updated when |
|---|---|
| `ghcr.io/vsamokhin/pod-manager:latest`, `:X.Y.Z`, `:X.Y` | a release is published |
| `ghcr.io/vsamokhin/pod-manager:edge` | every push to `main`, or a manual run of *Publish image* on a branch |

[`deploy/`](deploy/) has a compose file that runs production (`:latest`, port 8080) and a preview (`:edge`, port 8081) side by side with separate data, plus `update.sh` for cron: it pulls new images, backs up the production database before an update, and recreates only what changed. The server pulls; CI never needs access to it.

Verify an image: `cosign verify ghcr.io/vsamokhin/pod-manager:latest --certificate-identity-regexp 'https://github.com/VSamokhin/pod-manager/' --certificate-oidc-issuer https://token.actions.githubusercontent.com`

## Build and run with Docker Compose

```bash
git clone <this repo> pod-manager && cd pod-manager
cp .env.example .env          # optionally set POD_ADMIN_PASSWORD
docker compose up -d --build
```

Open http://your-server:8000 and log in with the admin account from `.env`. If you leave `POD_ADMIN_PASSWORD` empty, a random password is generated on first start and printed in `docker compose logs`.

The admin credentials in `.env` are only used when the database has no users yet. Change passwords afterwards under **Admin › Users** or **your username › Change password**.

### Data and backups

Everything lives in `./data` on the host:

| Path | Contents |
|---|---|
| `data/pod.db` | SQLite database |
| `data/files/originals/` | uploaded files, untouched |
| `data/files/thumbs/`, `previews/` | generated WebP previews |
| `data/secret.key` | session signing key |

To back up, stop the container (or use `sqlite3 data/pod.db ".backup backup.db"`) and copy the folder.

If the container can't write to `./data`, run `sudo chown -R 1000:1000 data` (the app runs as UID 1000).

### Updating

```bash
git pull && docker compose up -d --build
```

New tables are created automatically on start. There is no migration tool yet; columns added in future versions will need one (Alembic is the natural choice).

### HTTPS / remote access

The app speaks plain HTTP on port 8000. For access outside your LAN, put it behind a reverse proxy with TLS (Caddy, Traefik, nginx) or a VPN such as Tailscale, and set `POD_SECURE_COOKIES=1` when served over HTTPS.

## Configuration

| Variable | Default | |
|---|---|---|
| `POD_ADMIN_USERNAME` | `admin` | first admin, created on first start |
| `POD_ADMIN_PASSWORD` | random | printed to logs if not set |
| `POD_MAX_UPLOAD_MB` | `200` | per file |
| `POD_SECRET_KEY` | generated | session signing key |
| `POD_SECURE_COOKIES` | `0` | `1` behind HTTPS |
| `POD_DATA_DIR` | `/data` in Docker | |

## Roles

- **user**: upload, edit and flag images, create and edit drops, change drop states, assign goods, apply templates and export.
- **admin**: everything above, plus manage drop states, goods types, templates and users, and delete images and drops.

## How templates work

All template sizes are percentages of the image's shorter side, so one template works for a 600 px sketch and a 6000 px print file alike. The composition is a single SVG with the original file embedded at full resolution, so exports keep the source quality. Titles use fonts installed in the container (DejaVu and Liberation families, both free for commercial use). The text `{title}` in a title is replaced with the image's title.

The **Follow shape (sticker)** outline traces the image's transparency (PNG alpha or SVG) into a smooth vector path with the project's own small tracer (`app/outline.py`), fills holes, and grows it by the outline width. Images without transparency get a rounded rectangle. The optional cut line is drawn as a thin stroke in a separate colour (magenta by default) on the outer edge.

## Development

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
pre-commit install
POD_DATA_DIR=./data POD_ADMIN_PASSWORD=dev-password uvicorn app.main:app --reload
pytest --cov
```

Branch naming, versioning, releases and the quality gates are described in [CONTRIBUTING.md](CONTRIBUTING.md).

Cairo must be installed on the host for CairoSVG (`apt install libcairo2`, `brew install cairo`).

## Layout

```
app/
  main.py         app factory, login/logout/account
  auth.py         password hashing, role checks, first-run seeding
  db.py           SQLAlchemy models
  imaging.py      ingest, thumbnails/previews, contour mask
  outline.py      bitmap → smooth vector outline
  render.py       template parameters → SVG, PNG/PDF/SVG export
  routes/         images, drops, admin
  templates/      Jinja2 pages
  static/         CSS and a little JS (live preview, bulk select, drag & drop)
tests/            end-to-end tests and a dependency licence check
```

## License

POD Manager is free software under the [MIT License](LICENSE): use, modify and redistribute it, commercially or not, as long as the licence text is kept.

All dependencies are permissively licensed, except CairoSVG (LGPL-3.0), which is used unmodified as a separate library and is compatible with MIT. Details, including the fonts used in exported artwork, are in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

When adding a dependency, keep it under a permissive licence (MIT, BSD, Apache-2.0, ISC, PSF, ...) or LGPL used as an unmodified library, and add it to `THIRD_PARTY_NOTICES.md`. `pytest` fails if a GPL, AGPL, SSPL or similar copyleft package enters the runtime dependencies.
