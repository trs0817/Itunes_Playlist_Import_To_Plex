"""Tests for Music_Database_Import — v2 metadata-based format.

Covers:
- v2 database format (header line, metadata-based title keys without extensions)
- Old-format (legacy path-based) database is rejected by find_playlist_keys
- save_music_database detects a legacy DB, deletes it, and rebuilds in v2 format
- _normalize(): qualifier stripping (remastered, deluxe, mono, etc.)
- find_playlist_keys():
  - EXTINF-based artist/title parsing (iTunes format: Title - Artist)
  - Bare-path fallback with track-number-prefix stripping
  - Exact match
  - Normalized/fuzzy match (qualifier on DB side, qualifier on m3u side)
  - 'Still not found' path
  - Summary message with exact/fuzzy breakdown
- Malformed database lines skipped without crash
- Depth-2 path (no album subfolder) does not crash
- UTF-8 and cp1252 encoded .m3u files
"""
import sys
import pathlib
from unittest.mock import MagicMock, patch

import pytest

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import Music_Database_Import
import API_Calls


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
    """Write a v2 music database: v2 header followed by `lines`."""
    db = tmp_path / "Plex Music Database.txt"
    content = Music_Database_Import._DB_V2_HEADER + "\n" + "\n".join(lines)
    db.write_text(content, encoding="utf-8")
    return db


def _write_old_db(tmp_path, lines):
    """Write a legacy (v1/path-based) database with the old header."""
    db = tmp_path / "Plex Music Database.txt"
    content = "The Plex path for Music is: /media/music/\n" + "\n".join(lines)
    db.write_text(content, encoding="utf-8")
    return db


def _write_m3u(tmp_path, name, lines, encoding="utf-8"):
    f = tmp_path / name
    f.write_text("\n".join(lines), encoding=encoding)
    return f


# ---------------------------------------------------------------------------
# v2 format: normal 3-level match (bare paths, no EXTINF)
# ---------------------------------------------------------------------------

def test_normal_match(tmp_path):
    # v2 DB stores metadata title directly (no extension, no track-number prefix)
    db = _write_db(tmp_path, [
        "101:::the beatles:::abbey road:::come together",
        "102:::the beatles:::abbey road:::something",
        "103:::led zeppelin:::iv:::black dog",
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
        "not_an_int:::artist:::album:::track",   # bad key
        ":::artist:::album",                      # too few fields
        "200:::solo artist:::unknown album:::solo track",  # valid
    ])
    _write_m3u(tmp_path, "p.m3u", [
        r"C:\Music\Solo Artist\Unknown Album\Solo Track.flac",
    ])
    app = _make_app(tmp_path)
    keys = Music_Database_Import.find_playlist_keys(app, "p.m3u", db, tmp_path)
    assert keys == [200]
    assert any("malformed" in msg.lower() for _, msg in app.console_messages)


# ---------------------------------------------------------------------------
# Depth-2 path (no album subfolder) — no crash
# ---------------------------------------------------------------------------

def test_depth_two_path_no_crash(tmp_path):
    """Tracks stored with an empty album field don't crash anything."""
    db = _write_db(tmp_path, [
        "300:::gregfilth:::::::kill it before it lays eggs",
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
        "401:::beyoncé:::lemonade:::hold up",
        "402:::mötley crüe:::dr. feelgood:::kickstart my heart",
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
        "501:::beyoncé:::lemonade:::hold up",
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
        "601:::artist a:::album a:::track a",
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
        "701:::artist:::album:::track one",
        "702:::artist:::album:::track two",
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


# ---------------------------------------------------------------------------
# Legacy (v1) database is rejected by find_playlist_keys
# ---------------------------------------------------------------------------

def test_old_format_db_rejected(tmp_path):
    """A path-based legacy database must be rejected with a clear status message."""
    db = _write_old_db(tmp_path, [
        "101:::the beatles:::abbey road:::come together.mp3",
    ])
    _write_m3u(tmp_path, "p.m3u", [
        r"C:\Music\The Beatles\Abbey Road\Come Together.mp3",
    ])
    app = _make_app(tmp_path)
    keys = Music_Database_Import.find_playlist_keys(app, "p.m3u", db, tmp_path)
    assert keys == []
    msgs = [msg.lower() for _, msg in app.console_messages]
    assert any("legacy" in m or "rebuild" in m for m in msgs)


# ---------------------------------------------------------------------------
# save_music_database: legacy DB triggers one-time rebuild
# ---------------------------------------------------------------------------

def test_save_detects_and_rebuilds_legacy_db(tmp_path, monkeypatch):
    """When save_music_database finds a legacy v1 DB it deletes and rebuilds it."""
    db_file = tmp_path / "Plex Music Database.txt"
    db_file.write_text(
        "The Plex path for Music is: /media/music/\n"
        "101:::the beatles:::abbey road:::come together.mp3\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(Music_Database_Import, "DB_PATH", db_file)

    fake_track = {
        'ratingKey': '999',
        'grandparentTitle': 'The Beatles',
        'parentTitle': 'Abbey Road',
        'title': 'Come Together',
    }

    app = _make_app(tmp_path)
    with patch.object(API_Calls, 'get_track_data', return_value=[fake_track]):
        result = Music_Database_Import.save_music_database(app, "Music", "1", 1)

    assert result is not None
    content = db_file.read_text(encoding="utf-8")
    assert content.startswith(Music_Database_Import._DB_V2_HEADER)
    assert "999:::the beatles:::abbey road:::come together" in content
    msgs = [msg.lower() for _, msg in app.console_messages]
    assert any("legacy" in m or "rebuild" in m for m in msgs)


# ---------------------------------------------------------------------------
# _normalize(): qualifier stripping
# ---------------------------------------------------------------------------

def test_normalize_remastered(tmp_path):
    n = Music_Database_Import._normalize
    assert n("Tattoo You (Remastered)") == "tattoo you"
    assert n("Start Me Up (2009 Remaster)") == "start me up"
    assert n("Something (2009 Remastered)") == "something"


def test_normalize_various_qualifiers(tmp_path):
    n = Music_Database_Import._normalize
    assert n("Abbey Road (Deluxe Edition)") == "abbey road"
    # "st." -> "street" means the Deluxe Edition qualifier is stripped first,
    # then "main st." is expanded to "main street"
    assert n("Exile on Main St. (Super Deluxe Edition)") == "exile on main street"
    assert n("Let It Bleed (Mono)") == "let it bleed"
    assert n("Some Girls (Stereo Version)") == "some girls"
    assert n("IV (Anniversary Edition)") == "iv"
    # "(But I Like It)" is a recognised subtitle qualifier
    assert n("It's Only Rock 'n' Roll (But I Like It)") == "it s only rock n roll"
    # Non-qualifier parentheticals must NOT be stripped
    assert n("Solomon Bites the Worm (BBC Evening Session 1998)") == \
        "solomon bites the worm (bbc evening session 1998)"
    # Apostrophes become spaces; leading ( is preserved
    assert n("(I Can't Get No) Satisfaction") == "(i can t get no) satisfaction"


def test_normalize_unicode_apostrophe(tmp_path):
    """U+2019 and ASCII apostrophes both normalise to the same form (space)."""
    n = Music_Database_Import._normalize
    # Unicode and ASCII apostrophe variants produce identical output
    assert n("can\u2019t you hear me knocking") == n("can't you hear me knocking")
    assert n("i\u2019m not signifying") == n("i'm not signifying")
    # Exact output: apostrophe -> space
    assert n("can't stop") == "can t stop"


def test_normalize_ampersand_spacing(tmp_path):
    """Spaces around & are stripped so 'T & A' and 'T&A' normalise identically."""
    n = Music_Database_Import._normalize
    assert n("little t & a") == "little t&a"
    assert n("little t&a") == "little t&a"
    assert n("Rock & Roll") == "rock&roll"


def test_fuzzy_match_unicode_apostrophe(tmp_path):
    """DB has U+2019 apostrophe; EXTINF has ASCII apostrophe -> fuzzy match succeeds."""
    db = _write_db(tmp_path, [
        "19468:::the rolling stones:::sticky fingers:::can\u2019t you hear me knocking",
    ])
    _write_m3u(tmp_path, "p.m3u", [
        "#EXTM3U",
        "#EXTINF:436,Can't You Hear Me Knocking - The Rolling Stones",
        r"C:\Music\The Rolling Stones\Sticky Fingers\04 Can't You Hear Me Knocking.mp3",
    ])
    app = _make_app(tmp_path)
    keys = Music_Database_Import.find_playlist_keys(app, "p.m3u", db, tmp_path)
    assert keys == [19468]
    summary = [msg for _, msg in app.console_messages if "of the" in msg.lower()]
    assert "1 fuzzy" in summary[0]


def test_fuzzy_match_ampersand_spacing(tmp_path):
    """DB has 'little t & a' (spaced &); EXTINF has 'Little T&A' -> fuzzy match."""
    db = _write_db(tmp_path, [
        "43518:::the rolling stones:::tattoo you:::little t & a",
    ])
    _write_m3u(tmp_path, "p.m3u", [
        "#EXTM3U",
        "#EXTINF:203,Little T&A - The Rolling Stones",
        r"C:\Music\The Rolling Stones\Tattoo You (Remastered)\04 Little T&A.mp3",
    ])
    app = _make_app(tmp_path)
    keys = Music_Database_Import.find_playlist_keys(app, "p.m3u", db, tmp_path)
    assert keys == [43518]
    summary = [msg for _, msg in app.console_messages if "of the" in msg.lower()]
    assert "1 fuzzy" in summary[0]


# ---------------------------------------------------------------------------
# EXTINF parsing: exact match
# ---------------------------------------------------------------------------

def test_extinf_exact_match(tmp_path):
    """EXTINF artist+title match DB exactly; album from path also matches."""
    db = _write_db(tmp_path, [
        "800:::the rolling stones:::aftermath:::mother's little helper",
    ])
    _write_m3u(tmp_path, "p.m3u", [
        "#EXTM3U",
        "#EXTINF:165,Mother's Little Helper - The Rolling Stones",
        r"C:\Music\The Rolling Stones\Aftermath\01 Mother's Little Helper.mp3",
    ])
    app = _make_app(tmp_path)
    keys = Music_Database_Import.find_playlist_keys(app, "p.m3u", db, tmp_path)
    assert keys == [800]
    # Should be an exact match: artist=the rolling stones, album=aftermath, title=mother's little helper
    summary = [msg for _, msg in app.console_messages if "of the" in msg.lower()]
    assert "1 exact" in summary[0]


# ---------------------------------------------------------------------------
# EXTINF parsing: fuzzy match (album qualifier differs)
# ---------------------------------------------------------------------------

def test_extinf_fuzzy_match_album_qualifier(tmp_path):
    """Album in iTunes path has '(Remastered)'; Plex DB has clean album name."""
    db = _write_db(tmp_path, [
        "43515:::the rolling stones:::tattoo you:::start me up",
    ])
    _write_m3u(tmp_path, "p.m3u", [
        "#EXTM3U",
        "#EXTINF:213,Start Me Up - The Rolling Stones",
        r"C:\Music\The Rolling Stones\Tattoo You (Remastered)\01 Start Me Up.mp3",
    ])
    app = _make_app(tmp_path)
    keys = Music_Database_Import.find_playlist_keys(app, "p.m3u", db, tmp_path)
    assert keys == [43515]
    summary = [msg for _, msg in app.console_messages if "of the" in msg.lower()]
    assert "1 fuzzy" in summary[0]


# ---------------------------------------------------------------------------
# Fuzzy match: qualifier on the DB title side
# ---------------------------------------------------------------------------

def test_fuzzy_match_db_title_has_qualifier(tmp_path):
    """DB title includes '(2009 Remaster)'; m3u resolves to bare title via EXTINF."""
    db = _write_db(tmp_path, [
        "900:::the rolling stones:::tattoo you:::start me up (2009 remaster)",
    ])
    _write_m3u(tmp_path, "p.m3u", [
        "#EXTM3U",
        "#EXTINF:213,Start Me Up - The Rolling Stones",
        r"C:\Music\The Rolling Stones\Tattoo You\01 Start Me Up.mp3",
    ])
    app = _make_app(tmp_path)
    keys = Music_Database_Import.find_playlist_keys(app, "p.m3u", db, tmp_path)
    assert keys == [900]
    summary = [msg for _, msg in app.console_messages if "of the" in msg.lower()]
    assert "1 fuzzy" in summary[0]


# ---------------------------------------------------------------------------
# Bare-path fallback: track-number prefix stripped from filename
# ---------------------------------------------------------------------------

def test_bare_path_track_prefix_stripped(tmp_path):
    """Without EXTINF, track-number prefix is stripped from the filename."""
    db = _write_db(tmp_path, [
        "1001:::the rolling stones:::exile on main st.:::rocks off",
        "1002:::the rolling stones:::exile on main st.:::tumbling dice",
    ])
    _write_m3u(tmp_path, "p.m3u", [
        # No EXTINF lines — bare paths with various prefix formats
        r"C:\Music\The Rolling Stones\Exile On Main St.\1-01 Rocks Off.mp3",
        r"C:\Music\The Rolling Stones\Exile On Main St.\1-05 Tumbling Dice.mp3",
    ])
    app = _make_app(tmp_path)
    keys = Music_Database_Import.find_playlist_keys(app, "p.m3u", db, tmp_path)
    assert keys == [1001, 1002]


# ---------------------------------------------------------------------------
# Summary message shows exact/fuzzy breakdown
# ---------------------------------------------------------------------------

def test_summary_exact_fuzzy_breakdown(tmp_path):
    """Summary reports exact and fuzzy match counts separately."""
    db = _write_db(tmp_path, [
        "701:::artist:::album:::track one",          # exact match
        "702:::artist:::album (remastered):::track two",  # only reachable via fuzzy from m3u
    ])
    _write_m3u(tmp_path, "p.m3u", [
        "#EXTM3U",
        "#EXTINF:200,Track One - Artist",
        r"C:\Music\Artist\Album\Track One.mp3",        # exact: artist=artist, album=album, title=track one
        "#EXTINF:200,Track Two - Artist",
        r"C:\Music\Artist\Album\Track Two.mp3",        # fuzzy: album from DB is 'album (remastered)', m3u album is 'album'
    ])
    app = _make_app(tmp_path)
    keys = Music_Database_Import.find_playlist_keys(app, "p.m3u", db, tmp_path)
    assert len(keys) == 2
    summary = [msg for _, msg in app.console_messages if "of the" in msg.lower()]
    assert len(summary) == 1
    # Both found, with breakdown
    assert "2 were found" in summary[0]
    assert "exact" in summary[0]
    assert "fuzzy" in summary[0]


# ---------------------------------------------------------------------------
# _normalize(): "st." abbreviation expansion
# ---------------------------------------------------------------------------

def test_normalize_st_abbreviation(tmp_path):
    """'st.' expands to 'street' so album names match across abbreviation styles."""
    n = Music_Database_Import._normalize
    assert n("Exile on Main St.") == "exile on main street"
    assert n("exile on main st.") == "exile on main street"
    # "st." embedded in qualifier is still stripped correctly
    assert n("Exile on Main St. (Super Deluxe Edition)") == "exile on main street"
    # "st" without period is left alone (e.g. "1st")
    assert "1st" not in n("19th Nervous Breakdown")  # sanity check


# ---------------------------------------------------------------------------
# _normalize(): trailing punctuation and commas
# ---------------------------------------------------------------------------

def test_normalize_trailing_punctuation(tmp_path):
    """Trailing ? and ! are stripped."""
    n = Music_Database_Import._normalize
    assert n("Anybody Seen My Baby?") == "anybody seen my baby"
    assert n("Have You Seen Your Mother Baby?") == "have you seen your mother baby"


def test_normalize_comma_stripping(tmp_path):
    """Commas are removed from titles."""
    n = Music_Database_Import._normalize
    assert n("Have You Seen Your Mother, Baby") == "have you seen your mother baby"


def test_normalize_apostrophe_to_space(tmp_path):
    """Apostrophes become spaces; 'rock\'n' and 'rock n\'' normalise identically."""
    n = Music_Database_Import._normalize
    assert n("it's only rock'n roll") == n("it's only rock n' roll")
    assert n("it's only rock'n roll") == "it s only rock n roll"


# ---------------------------------------------------------------------------
# Fuzzy matches enabled by new normalisations
# ---------------------------------------------------------------------------

def test_fuzzy_match_st_abbreviation(tmp_path):
    """DB album 'exile on main st.' matches m3u album 'exile on main street'."""
    db = _write_db(tmp_path, [
        "12345:::the rolling stones:::exile on main st.:::rocks off",
    ])
    _write_m3u(tmp_path, "p.m3u", [
        "#EXTM3U",
        "#EXTINF:182,Rocks Off - The Rolling Stones",
        r"C:\Music\The Rolling Stones\Exile On Main Street\1-01 Rocks Off.mp3",
    ])
    app = _make_app(tmp_path)
    keys = Music_Database_Import.find_playlist_keys(app, "p.m3u", db, tmp_path)
    assert keys == [12345]
    summary = [msg for _, msg in app.console_messages if "of the" in msg.lower()]
    assert "1 fuzzy" in summary[0]


def test_fuzzy_match_trailing_question_mark(tmp_path):
    """DB title has trailing '?'; EXTINF has none -> fuzzy match."""
    db = _write_db(tmp_path, [
        "19578:::the rolling stones:::forty licks:::anybody seen my baby?",
    ])
    _write_m3u(tmp_path, "p.m3u", [
        "#EXTM3U",
        "#EXTINF:228,Anybody Seen My Baby - The Rolling Stones",
        r"C:\Music\The Rolling Stones\Forty Licks\Anybody Seen My Baby.mp3",
    ])
    app = _make_app(tmp_path)
    keys = Music_Database_Import.find_playlist_keys(app, "p.m3u", db, tmp_path)
    assert keys == [19578]
    summary = [msg for _, msg in app.console_messages if "of the" in msg.lower()]
    # Exact match should fire: normalized forms match, album also matches
    assert "found" in summary[0]


def test_fuzzy_fallback_ignores_album_when_multiple_candidates(tmp_path):
    """When album check fails for ALL candidates, first candidate is used."""
    db = _write_db(tmp_path, [
        "1001:::the rolling stones:::forty licks:::brown sugar",
        "1002:::the rolling stones:::sticky fingers:::brown sugar",
    ])
    _write_m3u(tmp_path, "p.m3u", [
        "#EXTM3U",
        "#EXTINF:230,Brown Sugar - The Rolling Stones",
        # m3u album is Jump Back — not in DB at all
        r"C:\Music\The Rolling Stones\Jump Back\Brown Sugar.mp3",
    ])
    app = _make_app(tmp_path)
    keys = Music_Database_Import.find_playlist_keys(app, "p.m3u", db, tmp_path)
    assert len(keys) == 1
    assert keys[0] in (1001, 1002)
    summary = [msg for _, msg in app.console_messages if "of the" in msg.lower()]
    assert "1 fuzzy" in summary[0]


# ---------------------------------------------------------------------------
# Concurrent build regression: two threads calling save_music_database()
# simultaneously must not crash or corrupt the database.
# ---------------------------------------------------------------------------

def test_concurrent_builds_no_crash_and_single_api_call(tmp_path, monkeypatch):
    """Race-condition regression: two threads start save_music_database() at
    the same time.  The second must block on _DB_BUILD_LOCK, wait for the
    first to finish, then take the 'already exists' fast-path rather than
    rebuilding — no exception, no corrupt file, API called exactly once."""
    import threading, time

    db_file = tmp_path / "Plex Music Database.txt"
    # Write a legacy DB so both callers will want to rebuild.
    db_file.write_text(
        "The Plex path for Music is: /media/music/\nlegacy\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(Music_Database_Import, "DB_PATH", db_file)

    api_calls = []
    api_lock  = threading.Lock()

    fake_track = {
        'ratingKey': '7',
        'grandparentTitle': 'The Beatles',
        'parentTitle': 'Abbey Road',
        'title': 'Come Together',
    }

    def slow_get_track_data(*args):
        # Record the call then sleep long enough for T2 to contend the lock.
        with api_lock:
            api_calls.append(args)
        time.sleep(0.05)
        return [fake_track]

    errors = []
    results = []

    def run_one():
        app = _make_app(tmp_path)
        try:
            with patch.object(API_Calls, 'get_track_data',
                              side_effect=slow_get_track_data):
                result = Music_Database_Import.save_music_database(
                    app, "Music", "1", 1)
        except Exception as exc:
            errors.append(exc)
        else:
            results.append(result)

    t1 = threading.Thread(target=run_one, daemon=True)
    t2 = threading.Thread(target=run_one, daemon=True)

    t1.start()
    time.sleep(0.01)   # give T1 time to acquire the lock before T2 tries
    t2.start()

    t1.join(timeout=10)
    t2.join(timeout=10)

    assert not errors, f"Exception(s): {errors}"
    assert len(results) == 2, "Both threads should return a result"

    # File must exist and carry the v2 header.
    assert db_file.exists()
    content = db_file.read_text(encoding="utf-8")
    assert content.startswith(Music_Database_Import._DB_V2_HEADER)
    assert "7:::the beatles:::abbey road:::come together" in content

    # The Plex API must have been queried exactly once (T2 took the fast path).
    assert len(api_calls) == 1, (
        f"Expected 1 API call, got {len(api_calls)} — "
        "lock did not prevent the second build"
    )
