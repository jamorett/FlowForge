"""Project .env loading for API credentials (no secrets committed)."""
import os


def test_dotenv_loads_key_from_project_env_file(tmp_path, monkeypatch) -> None:
    from flowforge.env import load_dotenv

    env_file = tmp_path / ".env"
    env_file.write_text("MODEL_API_KEY=test-key-from-file\n", encoding="utf-8")
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    assert load_dotenv(dotenv_path=env_file, override=True)
    assert os.environ.get("MODEL_API_KEY") == "test-key-from-file"


def test_real_environment_wins_over_file(tmp_path, monkeypatch) -> None:
    from flowforge.env import load_dotenv

    env_file = tmp_path / ".env"
    env_file.write_text("MODEL_API_KEY=file-key\n", encoding="utf-8")
    monkeypatch.setenv("MODEL_API_KEY", "real-key")
    load_dotenv(dotenv_path=env_file, override=False)
    assert os.environ.get("MODEL_API_KEY") == "real-key"


def test_missing_env_file_is_fine(tmp_path, monkeypatch) -> None:
    from flowforge.env import load_dotenv

    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    assert not load_dotenv(dotenv_path=tmp_path / ".env-does-not-exist")
    assert "MODEL_API_KEY" not in os.environ


def test_quotes_comments_and_export_prefix(tmp_path, monkeypatch) -> None:
    from flowforge.env import load_dotenv

    env_file = tmp_path / ".env"
    env_file.write_text(
        "# a comment\n\nexport MODEL_API_KEY='quoted-key'\nEMPTY=\nBOGUS LINE\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    assert load_dotenv(dotenv_path=env_file, override=True)
    assert os.environ.get("MODEL_API_KEY") == "quoted-key"
