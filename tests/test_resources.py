from soundmaster.resources import (
    get_app_icon,
    get_resource_dir,
    get_resource_path,
    get_settings_icon,
)


def test_resource_paths_exist() -> None:
    res_dir = get_resource_dir()
    assert res_dir.is_dir()

    png_path = get_resource_path("icon.png")
    ico_path = get_resource_path("icon.ico")
    settings_path = get_resource_path("settings.png")
    assert png_path.is_file()
    assert ico_path.is_file()
    assert settings_path.is_file()


def test_get_app_icon_returns_valid_icon() -> None:
    icon = get_app_icon()
    assert not icon.isNull()


def test_get_settings_icon_returns_valid_icon() -> None:
    icon = get_settings_icon()
    assert not icon.isNull()
