# Third-party software

POD Manager itself is released under the [MIT License](LICENSE).

This repository contains **only original source code**. No third-party code, fonts or binaries are copied into it. Dependencies are downloaded at install or image build time from their official sources, and each stays under its own licence. All of them allow use in an MIT-licensed project, including commercial use.

`tests/test_licenses.py` checks that no runtime Python dependency (direct or transitive) is under GPL, AGPL, SSPL or a similar copyleft or non-commercial licence. Run `pytest` before adding a dependency.

## Python packages (requirements.txt)

| Package | Licence | Notes |
|---|---|---|
| fastapi | MIT | web framework |
| uvicorn | BSD-3-Clause | ASGI server; `[standard]` extras are MIT / BSD / Apache-2.0 |
| jinja2 | BSD-3-Clause | HTML templates |
| python-multipart | Apache-2.0 | form and upload parsing |
| sqlalchemy | MIT | database layer |
| pillow | MIT-CMU (HPND) | raster images |
| cairosvg | LGPL-3.0-or-later | SVG → PNG/PDF rendering, see below |
| bcrypt | Apache-2.0 | password hashing |
| itsdangerous | BSD-3-Clause | signed session cookies |
| numpy | BSD-3-Clause | outline tracing |

Notable transitive dependencies: starlette (BSD-3-Clause), pydantic (MIT), cairocffi (BSD-3-Clause), cffi (MIT-0), tinycss2 / cssselect2 / webencodings (BSD-3-Clause), defusedxml (PSF-2.0), markupsafe (BSD-3-Clause), anyio (MIT).

Development only (`requirements-dev.txt`): pytest (MIT), httpx (BSD-3-Clause).

### About CairoSVG (LGPL-3.0)

CairoSVG is used as an unmodified library, installed separately by `pip` and imported at runtime. The LGPL allows this from software under any licence, including MIT. If you distribute a built Docker image, CairoSVG stays a separate, replaceable package inside it and its source is available from [PyPI](https://pypi.org/project/CairoSVG/) and [GitHub](https://github.com/Kozea/CairoSVG). If you modify CairoSVG itself, those changes must be released under the LGPL.

## System packages in the Docker image

Installed from Debian by the `Dockerfile`, not stored in this repository.

| Package | Licence |
|---|---|
| python:3.15-slim base image | PSF-2.0 (Python), Debian packages under their own free licences |
| libcairo2 | LGPL-2.1 or MPL-1.1 (dual) |
| fonts-dejavu-core | Bitstream Vera Fonts licence (permissive), DejaVu changes public domain |
| fonts-liberation2 | SIL Open Font License 1.1 |
| fontconfig | MIT-style (fontconfig licence) |

Each package's full licence is in `/usr/share/doc/<package>/copyright` inside the image.

## Fonts in exported artwork

Titles in exported PNG/PDF/SVG files are rendered with the fonts above. Both the Bitstream Vera licence and the SIL OFL 1.1 allow using the fonts in documents and products you create, including commercial print-on-demand goods, without restriction. PDF exports may embed font subsets, which both licences allow. If you add other fonts to the image, check that their licences allow commercial use and embedding.

## Your images

The artwork you upload and export stays yours. This software claims no rights over it.
