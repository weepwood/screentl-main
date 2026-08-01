import json

from screentl.settings import AppSettings, SettingsRepository


def test_settings_repository_round_trip(tmp_path):
    repository = SettingsRepository(tmp_path / "config.json")
    settings = AppSettings(
        folder=str(tmp_path / "captures"),
        interval=15,
        fps=30,
        audio=str(tmp_path / "music"),
        text="demo",
        startup=True,
        minimize_to_tray=False,
    )

    repository.save(settings)

    assert repository.load() == settings
    assert json.loads(repository.path.read_text(encoding="utf-8"))["fps"] == 30


def test_settings_repository_recovers_from_invalid_json(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{broken", encoding="utf-8")

    settings = SettingsRepository(path).load()

    assert settings.interval > 0
    assert settings.fps > 0
    assert settings.folder
