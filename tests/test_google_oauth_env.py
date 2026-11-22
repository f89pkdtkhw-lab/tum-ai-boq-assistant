"""tools/google_oauth_env.py: writes Google OAuth values into web/.env.local, keeps other lines, prints only ok."""
import importlib.util
import json
import stat
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("google_oauth_env", Path(__file__).resolve().parent.parent / "tools" / "google_oauth_env.py")
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def test_writes_values_keeps_lines_and_prints_only_ok(tmp_path, monkeypatch, capsys):
    ziel = tmp_path / "web" / ".env.local"
    ziel.parent.mkdir()
    ziel.write_text("# comment\nSTRIPE_SECRET_KEY=sk_test_x\nAUTH_GOOGLE_ID=old\nAUTH_SECRET=keep-me\n")
    monkeypatch.setattr(mod, "ZIEL", ziel)
    quelle = tmp_path / "client.json"
    quelle.write_text(json.dumps({"web": {"client_id": "cid.apps.googleusercontent.com", "client_secret": "GOCSPX-secret"}}))

    assert mod.main(["x", str(quelle)]) == 0
    out = capsys.readouterr()
    assert out.out == "ok\n" and "GOCSPX" not in out.out + out.err

    text = ziel.read_text()
    assert "# comment\nSTRIPE_SECRET_KEY=sk_test_x\n" in text
    assert "AUTH_GOOGLE_ID=cid.apps.googleusercontent.com" in text and "old" not in text
    assert "AUTH_GOOGLE_SECRET=GOCSPX-secret" in text
    assert "AUTH_SECRET=keep-me" in text
    assert "APP_URL=http://localhost:3000" in text
    assert stat.S_IMODE(ziel.stat().st_mode) == 0o600


def test_generates_auth_secret_when_missing(tmp_path, monkeypatch, capsys):
    ziel = tmp_path / ".env.local"
    monkeypatch.setattr(mod, "ZIEL", ziel)
    quelle = tmp_path / "c.json"
    quelle.write_text(json.dumps({"installed": {"client_id": "a", "client_secret": "b"}}))
    assert mod.main(["x", str(quelle)]) == 0
    zeilen = dict(z.split("=", 1) for z in ziel.read_text().splitlines())
    assert len(zeilen["AUTH_SECRET"]) == 64


def test_bad_json_fails_without_writing(tmp_path, monkeypatch, capsys):
    ziel = tmp_path / ".env.local"
    monkeypatch.setattr(mod, "ZIEL", ziel)
    quelle = tmp_path / "c.json"
    quelle.write_text("{}")
    assert mod.main(["x", str(quelle)]) == 1
    assert not ziel.exists()
