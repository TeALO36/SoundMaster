"""Updater tests.

The download and API paths run against a real local HTTP server rather than a
mock, because the parts that break in practice are streaming, sizes, and error
mapping — none of which a stubbed ``urlopen`` would exercise.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from soundmaster.core.updater import (
    InstallKind,
    ReleaseAsset,
    ReleaseInfo,
    UpdateError,
    _release_from_payload,
    choose_asset,
    download_asset,
    fetch_latest_release,
    is_newer,
    parse_version,
)

PAYLOAD_BYTES = b"SOUNDMASTER-INSTALLER-PAYLOAD" * 4096


class _Handler(BaseHTTPRequestHandler):
    release_json: bytes = b"{}"
    status: int = 200
    truncate: bool = False

    def log_message(self, *_args) -> None:  # keep pytest output clean
        return

    def do_GET(self) -> None:
        if self.path.startswith("/release"):
            if self.status != 200:
                self.send_error(self.status, "nope")
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(self.release_json)))
            self.end_headers()
            self.wfile.write(self.release_json)
            return
        if self.path.startswith("/asset"):
            body = PAYLOAD_BYTES[:-100] if self.truncate else PAYLOAD_BYTES
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404, "missing")


@pytest.fixture
def server():
    httpd = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=5)


def _base(server: HTTPServer) -> str:
    host, port = server.server_address[:2]
    return f"http://{host}:{port}"


def _payload(base: str, tag: str = "v9.9.9") -> dict:
    return {
        "tag_name": tag,
        "name": f"SoundMaster {tag}",
        "body": "Nouveautés",
        "html_url": "https://github.com/TeALO36/SoundMaster/releases/tag/" + tag,
        "assets": [
            {
                "name": f"SoundMaster-{tag}-Setup.exe",
                "browser_download_url": f"{base}/asset-exe",
                "size": len(PAYLOAD_BYTES),
            },
            {
                "name": f"SoundMaster-{tag}-Portable.zip",
                "browser_download_url": f"{base}/asset-zip",
                "size": len(PAYLOAD_BYTES),
            },
        ],
    }


def test_version_parsing_and_comparison() -> None:
    assert parse_version("v0.4.0") == (0, 4, 0)
    assert parse_version("0.10.2") == (0, 10, 2)
    assert parse_version("SoundMaster v1.2.3") == (1, 2, 3)
    assert parse_version("nightly") is None
    assert parse_version("") is None

    assert is_newer("v0.5.0", "0.4.0") is True
    assert is_newer("v0.4.1", "0.4.0") is True
    assert is_newer("v0.4.0", "0.4.0") is False
    assert is_newer("v0.3.9", "0.4.0") is False
    # 10 must beat 9: a string compare would get this wrong.
    assert is_newer("v0.10.0", "0.9.0") is True
    # An unreadable tag must never trigger an update.
    assert is_newer("nightly", "0.4.0") is False


def test_payload_parsing_rejects_unusable_entries() -> None:
    release = _release_from_payload(
        {
            "tag_name": "v1.0.0",
            "html_url": "https://example.com/r",
            "assets": [
                {"name": "ok.exe", "browser_download_url": "https://e.com/a", "size": 5},
                {"name": "insecure.exe", "browser_download_url": "http://e.com/b", "size": 5},
                {"name": "", "browser_download_url": "https://e.com/c", "size": 5},
                {"name": "bad-size.zip", "browser_download_url": "https://e.com/d", "size": "x"},
                "not-a-dict",
            ],
        }
    )
    assert [asset.name for asset in release.assets] == ["ok.exe", "bad-size.zip"]
    assert release.assets[1].size == 0

    with pytest.raises(UpdateError):
        _release_from_payload({"html_url": "https://example.com"})
    with pytest.raises(UpdateError):
        _release_from_payload(["not", "a", "dict"])


def test_asset_choice_follows_the_install_mode() -> None:
    release = ReleaseInfo(
        tag="v1.0.0",
        name="r",
        notes="",
        page_url="https://example.com",
        assets=(
            ReleaseAsset("SoundMaster-Setup.exe", "https://e/exe", 10),
            ReleaseAsset("SoundMaster-Portable.zip", "https://e/zip", 20),
        ),
    )
    assert choose_asset(release, InstallKind.INSTALLER).suffix == ".exe"
    assert choose_asset(release, InstallKind.PORTABLE).suffix == ".zip"

    # An MSI wins over the EXE when both are published.
    with_msi = ReleaseInfo(
        tag="v1.0.0",
        name="r",
        notes="",
        page_url="https://example.com",
        assets=release.assets + (ReleaseAsset("SoundMaster.msi", "https://e/msi", 30),),
    )
    assert with_msi.version == (1, 0, 0)
    assert choose_asset(with_msi, InstallKind.INSTALLER).suffix == ".msi"

    empty = ReleaseInfo(tag="v1.0.0", name="r", notes="", page_url="https://e", assets=())
    assert choose_asset(empty, InstallKind.INSTALLER) is None
    assert choose_asset(release, InstallKind.PORTABLE).name.endswith(".zip")


def test_fetch_latest_release_reads_a_real_response(server: HTTPServer) -> None:
    base = _base(server)
    _Handler.release_json = json.dumps(_payload(base)).encode("utf-8")
    _Handler.status = 200

    release = fetch_latest_release(url=f"{base}/release")

    assert release.tag == "v9.9.9"
    assert release.name == "SoundMaster v9.9.9"
    assert release.notes == "Nouveautés"
    assert release.page_url.endswith("v9.9.9")
    assert is_newer(release.tag) is True
    # The fixture serves plain HTTP, and an installer must never be fetched over
    # a channel that can be tampered with, so those assets are dropped.
    assert release.assets == ()

    secure = json.loads(_Handler.release_json.decode("utf-8"))
    for item in secure["assets"]:
        item["browser_download_url"] = item["browser_download_url"].replace(
            "http://", "https://"
        )
    _Handler.release_json = json.dumps(secure).encode("utf-8")
    https_release = fetch_latest_release(url=f"{base}/release")
    assert {asset.suffix for asset in https_release.assets} == {".exe", ".zip"}


def test_fetch_latest_release_maps_http_errors(server: HTTPServer) -> None:
    base = _base(server)
    _Handler.status = 404
    with pytest.raises(UpdateError, match="Aucune release"):
        fetch_latest_release(url=f"{base}/release")

    _Handler.status = 403
    with pytest.raises(UpdateError, match="limite temporairement"):
        fetch_latest_release(url=f"{base}/release")
    _Handler.status = 200


def test_fetch_latest_release_reports_an_unreachable_host() -> None:
    # Port 9 is the discard port: connecting must fail, not hang the UI thread.
    with pytest.raises(UpdateError, match="Connexion à GitHub impossible"):
        fetch_latest_release(timeout=2.0, url="http://127.0.0.1:9/release")


def test_download_asset_streams_to_disk_with_progress(
    server: HTTPServer, tmp_path: Path
) -> None:
    base = _base(server)
    _Handler.truncate = False
    asset = ReleaseAsset("SoundMaster-Setup.exe", f"{base}/asset-exe", len(PAYLOAD_BYTES))
    seen: list[tuple[int, int]] = []

    result = download_asset(asset, tmp_path / "updates", progress=lambda a, b: seen.append((a, b)))

    assert result == tmp_path / "updates" / "SoundMaster-Setup.exe"
    assert result.read_bytes() == PAYLOAD_BYTES
    assert seen, "progress must be reported while streaming"
    assert seen[-1][0] == len(PAYLOAD_BYTES)
    assert seen[-1][1] == len(PAYLOAD_BYTES)
    # No partial file may survive a successful download.
    assert list((tmp_path / "updates").glob("*.part")) == []


def test_download_asset_rejects_a_truncated_file(server: HTTPServer, tmp_path: Path) -> None:
    base = _base(server)
    _Handler.truncate = True
    asset = ReleaseAsset("SoundMaster-Setup.exe", f"{base}/asset-exe", len(PAYLOAD_BYTES))
    try:
        with pytest.raises(UpdateError, match="incomplet"):
            download_asset(asset, tmp_path / "updates")
    finally:
        _Handler.truncate = False
    # A rejected download must leave nothing behind to be launched later.
    assert not (tmp_path / "updates" / "SoundMaster-Setup.exe").exists()
    assert list((tmp_path / "updates").glob("*.part")) == []


def test_download_asset_can_be_cancelled(server: HTTPServer, tmp_path: Path) -> None:
    base = _base(server)
    asset = ReleaseAsset("SoundMaster-Setup.exe", f"{base}/asset-exe", len(PAYLOAD_BYTES))

    with pytest.raises(UpdateError, match="annulé"):
        download_asset(asset, tmp_path / "updates", cancelled=lambda: True)

    assert list((tmp_path / "updates").glob("*")) == []


def test_download_asset_reports_a_missing_url(server: HTTPServer, tmp_path: Path) -> None:
    base = _base(server)
    asset = ReleaseAsset("missing.exe", f"{base}/nope", 0)

    with pytest.raises(UpdateError, match="Téléchargement impossible"):
        download_asset(asset, tmp_path / "updates")
