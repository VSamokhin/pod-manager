"""Guard the project's MIT licence: no runtime dependency may be under a copyleft licence
that would force the combined work to change licence (GPL/AGPL/SSPL ...).

LGPL libraries are fine when used unmodified as separate packages; each one must be
listed explicitly below and in THIRD_PARTY_NOTICES.md.
"""

import re
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALLOWED_LGPL = {"cairosvg"}
FORBIDDEN = re.compile(
    r"\b(A?GPL|GNU (Affero )?General Public|SSPL|Server Side Public|EUPL|CC-BY-NC|Commons Clause)", re.I
)


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _license_text(dist: metadata.Distribution) -> str:
    md = dist.metadata
    parts = [md.get("License-Expression") or "", md.get("License") or ""]
    parts += [c for c in md.get_all("Classifier") or [] if c.startswith("License ::")]
    return " | ".join(p for p in parts if p)


def _runtime_closure() -> dict[str, metadata.Distribution]:
    todo = []
    for raw in (ROOT / "requirements.txt").read_text().splitlines():
        line = raw.split("#")[0].strip()
        if line:
            todo.append(_norm(re.split(r"[\[<>=!~; ]", line)[0]))
    seen: dict[str, metadata.Distribution] = {}
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            continue  # optional extra not installed here
        seen[name] = dist
        for req in dist.requires or []:
            if "extra ==" in req:
                continue
            todo.append(_norm(re.split(r"[\[<>=!~; (]", req)[0]))
    return seen


def test_no_copyleft_runtime_dependencies():
    offenders = []
    for name, dist in _runtime_closure().items():
        text = _license_text(dist)
        if name in ALLOWED_LGPL:
            assert "LGPL" in text or "Lesser" in text, f"{name} is no longer LGPL: {text}"
            continue
        if FORBIDDEN.search(text.replace("Lesser General Public", "").replace("LGPL", "")):
            offenders.append(f"{name}: {text}")
    assert not offenders, "Copyleft runtime dependencies found:\n" + "\n".join(offenders)


def test_every_direct_dependency_is_documented():
    notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text().lower()
    for line in (ROOT / "requirements.txt").read_text().splitlines():
        name = re.split(r"[\[<>=!~; ]", line.strip())[0]
        if name:
            assert name.lower() in notices, f"{name} missing from THIRD_PARTY_NOTICES.md"
