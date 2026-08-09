"""Update checks against the project's public GitHub releases.

Only the public Releases API is used: no token, no telemetry, and no automatic
background download. The user asks for a check, sees what would be installed,
and confirms before anything is written to disk or launched.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from soundmaster.core.config import is_portable_mode
from soundmaster.version import __version__

GITHUB_REPO = "TeALO36/SoundMaster"
RELEASES_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{GITHUB_REPO}/releases/latest"
USER_AGENT = f"SoundMaster/{__version__} (+https://github.com/{GITHUB_REPO})"

_VERSION_PATTERN = re.compile(r"(\d+)\.(\d+)\.(\d+)")


class UpdateError(RuntimeError):
    """Raised when the release feed cannot be read or an asset cannot be fetched."""


@dataclass(frozen=True, slots=True)
class ReleaseAsset:
    name: str
    url: str
    size: int

    @property
    def suffix(self) -> str:
        return Path(self.name).suffix.lower()


@dataclass(frozen=True, slots=True)
class ReleaseInfo:
    tag: str
    name: str
    notes: str
    page_url: str
    assets: tuple[ReleaseAsset, ...] = field(default_factory=tuple)

    @property
    def version(self) -> tuple[int, int, int] | None:
        return parse_version(self.tag)


def parse_version(text: str) -> tuple[int, int, int] | None:
    """Return a comparable MAJOR.MINOR.PATCH tuple, ignoring a leading ``v``."""

    match = _VERSION_PATTERN.search(text or "")
    if match is None:
        return None
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def current_version() -> tuple[int, int, int]:
    return parse_version(__version__) or (0, 0, 0)


def is_newer(candidate: str, installed: str = __version__) -> bool:
    """Compare two version strings; unreadable candidates are never 'newer'."""

    parsed = parse_version(candidate)
    if parsed is None:
        return False
    return parsed > (parse_version(installed) or (0, 0, 0))


def fetch_latest_release(timeout: float = 10.0, url: str = RELEASES_API) -> ReleaseInfo:
    """Read the latest published release from the public GitHub API."""

    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise UpdateError(
                "Aucune release publiée n’a été trouvée pour SoundMaster."
            ) from error
        if error.code in {403, 429}:
            raise UpdateError(
                "GitHub limite temporairement les requêtes. Réessayez dans quelques minutes."
            ) from error
        raise UpdateError(f"GitHub a répondu {error.code}.") from error
    except urllib.error.URLError as error:
        raise UpdateError(
            f"Connexion à GitHub impossible : {error.reason}. Vérifiez votre accès Internet."
        ) from error
    except (TimeoutError, OSError) as error:
        raise UpdateError(f"Connexion à GitHub impossible : {error}") from error
    except json.JSONDecodeError as error:
        raise UpdateError("Réponse GitHub illisible.") from error
    return _release_from_payload(payload)


def _release_from_payload(payload: object) -> ReleaseInfo:
    if not isinstance(payload, dict):
        raise UpdateError("Réponse GitHub inattendue.")
    assets: list[ReleaseAsset] = []
    raw_assets = payload.get("assets")
    if isinstance(raw_assets, list):
        for item in raw_assets:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            url = str(item.get("browser_download_url") or "").strip()
            if not name or not url.startswith("https://"):
                continue
            try:
                size = int(item.get("size") or 0)
            except (TypeError, ValueError):
                size = 0
            assets.append(ReleaseAsset(name=name, url=url, size=size))
    tag = str(payload.get("tag_name") or "").strip()
    if not tag:
        raise UpdateError("La release publiée n’a pas de tag de version.")
    return ReleaseInfo(
        tag=tag,
        name=str(payload.get("name") or tag).strip(),
        notes=str(payload.get("body") or "").strip(),
        page_url=str(payload.get("html_url") or RELEASES_PAGE).strip(),
        assets=tuple(assets),
    )


class InstallKind:
    """How this copy of SoundMaster was installed, which decides the update path."""

    INSTALLER = "installer"
    PORTABLE = "portable"
    SOURCE = "source"


def install_kind() -> str:
    """Detect installer, portable, or a source checkout."""

    if not getattr(sys, "frozen", False):
        return InstallKind.SOURCE
    return InstallKind.PORTABLE if is_portable_mode() else InstallKind.INSTALLER


def choose_asset(release: ReleaseInfo, kind: str | None = None) -> ReleaseAsset | None:
    """Pick the asset that matches how this copy was installed.

    An MSI is preferred over the Inno Setup EXE when both are published, so a
    future enterprise build is picked up without touching this code again.
    """

    kind = kind or install_kind()
    if kind == InstallKind.PORTABLE:
        wanted = (".zip",)
    else:
        wanted = (".msi", ".exe")
    for suffix in wanted:
        for asset in release.assets:
            if asset.suffix == suffix:
                return asset
    return None


def download_asset(
    asset: ReleaseAsset,
    destination_dir: Path,
    progress: Callable[[int, int], None] | None = None,
    timeout: float = 30.0,
    cancelled: Callable[[], bool] | None = None,
) -> Path:
    """Stream a release asset to disk, reporting progress as it goes."""

    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / asset.name
    partial = destination.with_suffix(destination.suffix + ".part")
    request = urllib.request.Request(asset.url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            try:
                total = int(response.headers.get("Content-Length") or asset.size or 0)
            except (TypeError, ValueError):
                total = asset.size
            completed = 0
            with partial.open("wb") as handle:
                while True:
                    if cancelled is not None and cancelled():
                        raise UpdateError("Téléchargement annulé.")
                    chunk = response.read(262_144)
                    if not chunk:
                        break
                    handle.write(chunk)
                    completed += len(chunk)
                    if progress is not None:
                        progress(completed, total)
    except UpdateError:
        partial.unlink(missing_ok=True)
        raise
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        partial.unlink(missing_ok=True)
        raise UpdateError(f"Téléchargement impossible : {error}") from error
    if asset.size and partial.stat().st_size != asset.size:
        partial.unlink(missing_ok=True)
        raise UpdateError(
            "Le fichier téléchargé est incomplet. Relancez la mise à jour."
        )
    destination.unlink(missing_ok=True)
    partial.replace(destination)
    return destination


def launch_installer(installer: Path) -> None:
    """Start the downloaded installer and let it replace this installation.

    The caller must close SoundMaster right after, because Windows cannot
    overwrite the running executable.
    """

    if not installer.is_file():
        raise UpdateError(f"Installateur introuvable : {installer}")
    suffix = installer.suffix.lower()
    try:
        if suffix == ".msi":
            subprocess.Popen(
                ["msiexec", "/i", str(installer)],
                close_fds=True,
            )
        elif suffix == ".exe":
            subprocess.Popen([str(installer)], close_fds=True)
        else:
            reveal_in_explorer(installer)
    except OSError as error:
        raise UpdateError(f"Lancement de l’installateur impossible : {error}") from error


def reveal_in_explorer(target: Path) -> None:
    """Open the folder holding a downloaded file, selecting it when possible."""

    try:
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", str(target)], close_fds=True)
        else:  # pragma: no cover - developer convenience only.
            os.startfile(str(target.parent))  # type: ignore[attr-defined]
    except (OSError, AttributeError) as error:
        raise UpdateError(f"Ouverture du dossier impossible : {error}") from error
