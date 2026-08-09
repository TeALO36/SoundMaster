"""Settings panel that checks for, downloads, and starts a SoundMaster update.

Every network call runs on a worker thread so the window never freezes, and the
user confirms each step: nothing is downloaded or launched implicitly.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QObject, Qt, QThread, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from soundmaster.core.updater import (
    InstallKind,
    ReleaseAsset,
    ReleaseInfo,
    UpdateError,
    choose_asset,
    download_asset,
    fetch_latest_release,
    install_kind,
    is_newer,
    launch_installer,
    reveal_in_explorer,
)
from soundmaster.version import __version__


def format_size(size: int) -> str:
    if size <= 0:
        return "taille inconnue"
    megabytes = size / (1024 * 1024)
    if megabytes >= 1:
        return f"{megabytes:.1f} Mo"
    return f"{size / 1024:.0f} Ko"


class UpdateCheckWorker(QObject):
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)

    def run(self) -> None:
        try:
            self.finished.emit(fetch_latest_release())
        except UpdateError as error:
            self.failed.emit(str(error))
        except Exception as error:  # noqa: BLE001 - network boundary must not crash the UI.
            self.failed.emit(f"Vérification impossible : {error}")


class UpdateDownloadWorker(QObject):
    finished = pyqtSignal(str)
    failed = pyqtSignal(str)
    progress = pyqtSignal(int, int)

    def __init__(self, asset: ReleaseAsset, destination: Path) -> None:
        super().__init__()
        self.asset = asset
        self.destination = destination
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            path = download_asset(
                self.asset,
                self.destination,
                progress=lambda done, total: self.progress.emit(done, total),
                cancelled=lambda: self._cancelled,
            )
        except UpdateError as error:
            self.failed.emit(str(error))
        except Exception as error:  # noqa: BLE001 - network boundary must not crash the UI.
            self.failed.emit(f"Téléchargement impossible : {error}")
        else:
            self.finished.emit(str(path))


class UpdateSettingsPanel(QWidget):
    """Check for a newer release and install it, whatever the install mode."""

    quit_requested = pyqtSignal()

    def __init__(self, download_dir: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("updatePanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.download_dir = download_dir
        self._thread: QThread | None = None
        self._worker: QObject | None = None
        self._release: ReleaseInfo | None = None
        self._asset: ReleaseAsset | None = None
        self._downloaded: Path | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        title = QLabel("Mises à jour")
        title.setObjectName("consentTitle")
        layout.addWidget(title)

        self.version_label = QLabel(f"Version installée : <b>{__version__}</b> · {self._mode_label()}")
        self.version_label.setTextFormat(Qt.TextFormat.RichText)
        self.version_label.setWordWrap(True)
        layout.addWidget(self.version_label)

        self.status_label = QLabel(
            "Cliquez sur « Vérifier les mises à jour » pour interroger GitHub. "
            "Rien n’est téléchargé sans votre accord."
        )
        self.status_label.setObjectName("muted")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.check_button = QPushButton("Vérifier les mises à jour")
        self.check_button.setObjectName("primaryButton")
        self.check_button.clicked.connect(self.check_for_updates)
        actions.addWidget(self.check_button)
        self.install_button = QPushButton("Télécharger et installer")
        self.install_button.setObjectName("compactButton")
        self.install_button.setVisible(False)
        self.install_button.clicked.connect(self._start_download)
        actions.addWidget(self.install_button)
        self.notes_button = QPushButton("Voir les nouveautés")
        self.notes_button.setObjectName("compactButton")
        self.notes_button.setVisible(False)
        self.notes_button.clicked.connect(self._open_release_page)
        actions.addWidget(self.notes_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.hint = QLabel(
            "SoundMaster ne se met jamais à jour tout seul en arrière-plan et "
            "n’envoie aucune donnée : seule la liste publique des releases est lue."
        )
        self.hint.setObjectName("muted")
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)

    # -- checking -----------------------------------------------------------

    def _mode_label(self) -> str:
        return {
            InstallKind.INSTALLER: "installation Windows",
            InstallKind.PORTABLE: "mode portable",
            InstallKind.SOURCE: "lancé depuis les sources",
        }.get(install_kind(), "mode inconnu")

    def check_for_updates(self) -> None:
        if self._thread is not None:
            return
        self.check_button.setEnabled(False)
        self.install_button.setVisible(False)
        self.notes_button.setVisible(False)
        self.status_label.setText("Vérification en cours sur GitHub…")
        worker = UpdateCheckWorker()
        worker.finished.connect(self._check_finished)
        worker.failed.connect(self._check_failed)
        self._start(worker)

    def _check_finished(self, release: object) -> None:
        # Reset first: no early return below may leave a stale install offer up.
        self.install_button.setVisible(False)
        self._asset = None
        if not isinstance(release, ReleaseInfo):
            self._check_failed("Réponse GitHub inattendue.")
            return
        self._release = release
        if not is_newer(release.tag):
            self.status_label.setText(
                f"SoundMaster est à jour (dernière release publiée : {release.tag})."
            )
            self.notes_button.setVisible(True)
            return
        # Derive the install mode once: asset choice and the message below must
        # never disagree about how this copy was installed.
        kind = install_kind()
        self._asset = choose_asset(release, kind)
        self.notes_button.setVisible(True)
        if self._asset is None:
            self.status_label.setText(
                f"La version {release.tag} est disponible, mais aucun fichier "
                "correspondant à votre installation n’est publié. Utilisez "
                "« Voir les nouveautés » pour la télécharger manuellement."
            )
            return
        if kind == InstallKind.SOURCE:
            self.status_label.setText(
                f"La version {release.tag} est disponible. Vous utilisez les sources : "
                "mettez à jour avec « git pull »."
            )
            return
        self.status_label.setText(
            f"Version <b>{release.tag}</b> disponible — {self._asset.name} "
            f"({format_size(self._asset.size)})."
        )
        self.status_label.setTextFormat(Qt.TextFormat.RichText)
        self.install_button.setVisible(True)

    def _check_failed(self, message: str) -> None:
        self.status_label.setText(message)

    # -- downloading --------------------------------------------------------

    def _start_download(self) -> None:
        if self._thread is not None or self._asset is None or self._release is None:
            return
        answer = QMessageBox.question(
            self,
            "Télécharger la mise à jour ?",
            f"Télécharger {self._asset.name} ({format_size(self._asset.size)}) "
            f"depuis la release {self._release.tag} de GitHub ?\n\n"
            "SoundMaster se fermera pour laisser l’installateur travailler.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.install_button.setEnabled(False)
        self.check_button.setEnabled(False)
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self.status_label.setText(f"Téléchargement de {self._asset.name}…")
        worker = UpdateDownloadWorker(self._asset, self.download_dir)
        worker.progress.connect(self._download_progress)
        worker.finished.connect(self._download_finished)
        worker.failed.connect(self._download_failed)
        self._start(worker)

    def _download_progress(self, completed: int, total: int) -> None:
        if total > 0:
            self.progress.setRange(0, 100)
            self.progress.setValue(min(100, int(completed * 100 / total)))
        else:
            self.progress.setRange(0, 0)

    def _download_finished(self, path_text: str) -> None:
        self._downloaded = Path(path_text)
        self.progress.setValue(100)
        if install_kind() == InstallKind.PORTABLE:
            self.status_label.setText(
                f"Archive téléchargée : {self._downloaded.name}. Fermez SoundMaster, "
                "puis remplacez le dossier portable par le contenu de l’archive."
            )
            try:
                reveal_in_explorer(self._downloaded)
            except UpdateError as error:
                self.status_label.setText(f"{self.status_label.text()} ({error})")
            return
        self.status_label.setText("Lancement de l’installateur…")
        try:
            launch_installer(self._downloaded)
        except UpdateError as error:
            self.status_label.setText(str(error))
            QMessageBox.warning(self, "Mise à jour", str(error))
            return
        self.quit_requested.emit()

    def _download_failed(self, message: str) -> None:
        self.progress.setVisible(False)
        self.status_label.setText(message)
        QMessageBox.warning(self, "Mise à jour", message)

    def _open_release_page(self) -> None:
        if self._release is None:
            return
        QDesktopServices.openUrl(QUrl(self._release.page_url))

    # -- worker plumbing ----------------------------------------------------

    def _start(self, worker: QObject) -> None:
        thread = QThread(self)
        self._thread, self._worker = thread, worker
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        for signal_name in ("finished", "failed"):
            getattr(worker, signal_name).connect(
                thread.quit, Qt.ConnectionType.DirectConnection
            )
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._thread_done)
        thread.start()

    def _thread_done(self) -> None:
        self._thread = None
        self._worker = None
        self.check_button.setEnabled(True)
        self.install_button.setEnabled(True)
        if self.progress.isVisible() and self.progress.value() >= 100:
            self.progress.setVisible(False)

    def stop(self) -> None:
        """Cancel any in-flight work so the window can close immediately."""

        worker = self._worker
        if isinstance(worker, UpdateDownloadWorker):
            worker.cancel()
        thread = self._thread
        if thread is not None and thread.isRunning():
            thread.quit()
            thread.wait(5000)
