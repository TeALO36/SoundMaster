# Windows packaging

SoundMaster ships two Windows distribution formats:

- `SoundMaster-v<version>-Setup.exe`: a per-user Inno Setup **EXE installer** (not MSI). It installs under the user's local programs directory and creates a Start Menu shortcut. This format is suitable for normal Windows users; a true MSI can be added later for enterprise Group Policy deployment.
- `SoundMaster-v<version>-Portable.zip`: a PyInstaller `onedir` folder with a `.portable` marker. Runtime data is stored in a `data` folder beside the executable.

## Local build prerequisites

- Windows
- Python 3.11–3.14
- Inno Setup 6 (`ISCC.exe`) available on `PATH`

From the repository root:

```powershell
python -m pip install ".[dev,build]"
.\packaging\build_windows.ps1 -Version 0.5.0
```

The outputs are written to `dist/` and `dist/installer/`. The script cleans those build directories, verifies that the requested version matches `pyproject.toml`, writes a temporary runtime version module, runs the checked-in `SoundMaster.spec`, creates the portable marker and ZIP, compiles the installer, and removes the temporary version module. Bump `pyproject.toml` before creating a release tag.

PyInstaller uses `onedir` intentionally. It avoids the slower temporary extraction behavior of `onefile` builds and is generally less likely to trigger antivirus heuristics. UPX compression is disabled.

## GitHub releases

The workflow `.github/workflows/release.yml` runs on tags matching:

```text
vMAJOR.MINOR.PATCH
```

For example, after bumping the version in `pyproject.toml`:

```powershell
git tag v0.5.0
git push origin v0.5.0
```

GitHub Actions then runs tests, builds both artifacts on `windows-2022`, uploads workflow artifacts, and attaches the ZIP and installer to a generated GitHub Release. The workflow needs the repository's default `GITHUB_TOKEN` to have `contents: write` permission; the workflow declares this explicitly.

A manual dispatch is also available when an existing version tag is supplied.

## Signing

The generated files are unsigned. For public commercial distribution, configure a code-signing certificate and sign the executable and installer in the workflow before publishing. Keep the signing certificate in a dedicated secret or external signing service; never commit a private key. Unsigned Windows binaries may trigger SmartScreen warnings even when the build is legitimate. The installer currently points to `https://github.com/TeALO36/SoundMaster`. Update it if the publisher website changes before a public release.

The source-code license and third-party notices are documented in [`LICENSE`](../LICENSE) and [`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md). Re-check those notices for every dependency and model revision before shipping an installer or portable archive.

## Portable mode

Portable mode is enabled only for a frozen executable next to a `.portable` marker. It writes:

```text
<portable-folder>\data\
```

The installed version has no marker and uses `%LOCALAPPDATA%\SoundMaster\`, so it does not require write access under `Program Files`.
