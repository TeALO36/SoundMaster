from pathlib import Path
from types import SimpleNamespace

from soundmaster.core.config import AppPaths
from soundmaster.ui.main_window import collect_gpu_diagnostics


def _paths(tmp_path: Path) -> AppPaths:
    data = tmp_path / "data"
    return AppPaths(
        data_dir=data,
        database=data / "soundmaster.db",
        legal_profile=data / "legal.json",
        models=data / "models",
        audio_cache=data / "audio-cache",
        voice_samples=data / "voice-samples",
        logs=data / "logs",
    )


def test_gpu_diagnostics_reports_cuda_and_memory(monkeypatch, tmp_path: Path) -> None:
    class FakeCuda:
        @staticmethod
        def is_available() -> bool:
            return True

        @staticmethod
        def current_device() -> int:
            return 0

        @staticmethod
        def get_device_properties(_device: int) -> SimpleNamespace:
            return SimpleNamespace(name="Test RTX", total_memory=8 * 1024**3)

        @staticmethod
        def memory_allocated(_device: int) -> int:
            return 2 * 1024**3

        @staticmethod
        def memory_reserved(_device: int) -> int:
            return 3 * 1024**3

        @staticmethod
        def is_bf16_supported() -> bool:
            return True

    fake_torch = SimpleNamespace(
        __version__="2.11.0+cu126",
        version=SimpleNamespace(cuda="12.6"),
        cuda=FakeCuda,
    )
    monkeypatch.setitem(__import__("sys").modules, "torch", fake_torch)
    monkeypatch.setattr("soundmaster.ui.main_window.importlib.util.find_spec", lambda name: object())

    report = collect_gpu_diagnostics(_paths(tmp_path))

    assert "GPU : Test RTX" in report
    assert "VRAM : 8.0 Go total" in report
    assert "CUDA : 12.6" in report
    assert "BF16 : oui" in report
    assert "Mode : CUDA + BF16/FP16 + inference_mode" in report


def test_gpu_diagnostics_reports_cpu_fallback(monkeypatch, tmp_path: Path) -> None:
    class FakeCuda:
        @staticmethod
        def is_available() -> bool:
            return False

    fake_torch = SimpleNamespace(
        __version__="2.11.0+cpu",
        version=SimpleNamespace(cuda=None),
        cuda=FakeCuda,
    )
    monkeypatch.setitem(__import__("sys").modules, "torch", fake_torch)
    monkeypatch.setattr("soundmaster.ui.main_window.importlib.util.find_spec", lambda name: object())

    report = collect_gpu_diagnostics(_paths(tmp_path))

    assert "PyTorch : 2.11.0+cpu" in report
    assert "Accélération : CPU" in report
    assert "setup_gpu.bat" in report
