"""Tests for Music_Database_Import.find_playlist_keys()

Covers:
- Normal 3-level path matching (artist/album/track)
- Malformed database lines are skipped without crashing
- Depth-2 path (artist/track, no album) — documents current behaviour
- UTF-8 encoded .m3u file (with accented characters)
- cp1252 encoded .m3u file (with accented characters)
- Track not in database produces a warning, not a crash
- Summary message reports correct counts

Note: the database stores the full filename (with extension) as the track
field — e.g. "come together.mp3", not "come together".  Test fixtures must
match this exactly.
"""
import sys
import pathlib
from unittest.mock import MagicMock

import pytest

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import Music_Database_Import


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_app(tmp_path):
    app = MagicMock()
    app.console_messages = []

    def _post(msg, tag="info"):
        app.console_messages.append((tag, msg))

    app.post_to_status_console.side_effect = _post
    return app


def _write_db(tmp_path, lines):
    """Write a music database with a header line followed by `lines`."""
    db = tmp_path / "Plex Music Database.txt"
    content = "The Plex path for Music is: /media/music/\n" + "\n".join(lines)
    db.write_text(content, encoding="utf-8")
    return db


def _write_m3u(tmp_path, name, lines, encoding="utf-8"):
    f = tmp_path / name
    f.write_text("\n".join(lines), encoding=encoding)
    return f


# ---------------------------------------------------------------------------
# Normal 3-level match
# ---------------------------------------------------------------------------

def test_normal_match(tmp_path):
    # DB stores full filenames (with extension) as the track field
    db = _write_db(tmp_path, [
        "101:::the beatles:::abbey road:::come together.mp3",
        "102:::the beatles:::abbey road:::something.mp3",
        "103:::led zeppelin:::iv:::black dog.mp3",
    ])
    _write_m3u(tmp_path, "playlist.m3u", [
        "#EXTM3U",
        r"C:\Music\The Beatles\Abbey Road\Come Together.mp3",
        r"C:\Music\Led Zeppelin\IV\Black Dog.mp3",
    ])
    app = _make_app(tmp_path)
    keys = Music_Database_Import.find_playlist_keys(app, "playlist.m3u", db, tmp_path)
    assert keys == [101, 103]
    assert any("2 were found" in msg for _, msg in app.console_messages)


# ---------------------------------------------------------------------------
# Malformed database lines are skipped, no crash
# ---------------------------------------------------------------------------

def test_malformed_db_lines_skipped(tmp_path):
    db = _write_db(tmp_path, [
        "not_an_int:::artist:::album:::track.flac",   # bad key
        ":::artist:::album",                            # too few fields
        "200:::solo artist:::unknown album:::solo track.flac",  # valid
    ])
    _write_m3u(tmp_path, "p.m3u", [
        r"C:\Music\Solo Artist\Unknown Album\Solo Track.flac",
    ])
    app = _make_app(tmp_path)
    keys = Music_Database_Import.find_playlist_keys(app, "p.m3u", db, tmp_path)
    assert keys == [200]
    assert any("malformed" in msg.lower() for _, msg in app.console_messages)


# ---------------------------------------------------------------------------
# Depth-2 path (no album subfolder) — documents the current behaviour
# ---------------------------------------------------------------------------

def test_depth_two_path_no_crash(tmp_path):
    """Tracks stored with an empty album field don't crash anything."""
    db = _write_db(tmp_path, [
        "300:::gregfilth:::::::kill it before it lays eggs.flac",
    ])
    _write_m3u(tmp_path, "p.m3u", [
        r"C:\Music\GregFilth\Kill It Before It Lays Eggs.flac",
    ])
    app = _make_app(tmp_path)
    keys = Music_Database_Import.find_playlist_keys(app, "p.m3u", db, tmp_path)
    # No crash is the primary assertion; match behaviour is documented
    assert isinstance(keys, list)


# ---------------------------------------------------------------------------
# UTF-8 encoded .m3u with accented characters
# ---------------------------------------------------------------------------

def test_utf8_accented(tmp_path):
    db = _write_db(tmp_path, [
        "401:::beyoncé:::lemonade:::hold up.mp3",
        "402:::mötley crüe:::dr. feelgood:::kickstart my heart.mp3",
    ])
    _write_m3u(tmp_path, "acc.m3u", [
        "C:/Music/Beyoncé/Lemonade/Hold Up.mp3",
        "C:/Music/Mötley Crüe/Dr. Feelgood/Kickstart My Heart.mp3",
    ], encoding="utf-8")
    app = _make_app(tmp_path)
    keys = Music_Database_Import.find_playlist_keys(app, "acc.m3u", db, tmp_path)
    assert 401 in keys
    assert 402 in keys


# ---------------------------------------------------------------------------
# cp1252 encoded .m3u with accented characters
# ---------------------------------------------------------------------------

def test_cp1252_accented(tmp_path):
    db = _write_db(tmp_path, [
        "501:::beyoncé:::lemonade:::hold up.mp3",
    ])
    m3u_path = tmp_path / "cp.m3u"
    m3u_path.write_bytes(
        "C:/Music/Beyoncé/Lemonade/Hold Up.mp3\n".encode("cp1252")
    )
    app = _make_app(tmp_path)
    keys = Music_Database_Import.find_playlist_keys(app, "cp.m3u", db, tmp_path)
    assert 501 in keys


# ---------------------------------------------------------------------------
# Missing track — warning posted, no crash
# ---------------------------------------------------------------------------

def test_missing_track_posts_warning(tmp_path):
    db = _write_db(tmp_path, [
        "601:::artist a:::album a:::track a.mp3",
    ])
    _write_m3u(tmp_path, "p.m3u", [
        r"C:\Music\Artist A\Album A\Track A.mp3",
        r"C:\Music\Artist B\Album B\Track B.mp3",  # not in db
    ])
    app = _make_app(tmp_path)
    keys = Music_Database_Import.find_playlist_keys(app, "p.m3u", db, tmp_path)
    assert keys == [601]
    assert any("not found" in msg.lower() for _, msg in app.console_messages)


# ---------------------------------------------------------------------------
# Summary message
# ---------------------------------------------------------------------------

def test_summary_message(tmp_path):
    db = _write_db(tmp_path, [
        "701:::artist:::album:::track one.mp3",
        "702:::artist:::album:::track two.mp3",
    ])
    _write_m3u(tmp_path, "p.m3u", [
        r"C:\Music\Artist\Album\Track One.mp3",
        r"C:\Music\Artist\Album\Track Two.mp3",
        r"C:\Music\Artist\Album\Track Three.mp3",  # missing
    ])
    app = _make_app(tmp_path)
    keys = Music_Database_Import.find_playlist_keys(app, "p.m3u", db, tmp_path)
    assert len(keys) == 2
    summary = [msg for _, msg in app.console_messages if "of the" in msg.lower()]
    assert len(summary) == 1
    assert "3 tracks" in summary[0]
    assert "2 were found" in summary[0]
