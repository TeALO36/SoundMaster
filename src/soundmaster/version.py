"""Application version exposed to the UI and packaged executable."""

try:
    from soundmaster._build_version import __version__
except ImportError:
    __version__ = "0.8.9"
