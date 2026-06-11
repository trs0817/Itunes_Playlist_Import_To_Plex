# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ultimation LLC and Robert C Suffern
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import os
import re
import threading
from pathlib import Path

import API_Calls
from API_Calls import PlexConnectionError

# Fixed storage location: %LOCALAPPDATA%\iTunesToPlex\Plex Music Database.txt
_APP_DIR = Path(os.getenv("LOCALAPPDATA", "")) / "iTunesToPlex"
if not str(_APP_DIR).strip("/\\"):
    # LOCALAPPDATA not set (non-Windows fallback)
    _APP_DIR = Path.home() / "AppData" / "Local" / "iTunesToPlex"

DB_PATH = _APP_DIR / "Plex Music Database.txt"

# Serialises concurrent save_music_database() calls (e.g. Rebuild button
# clicked while an import is already building the database).  The second
# caller blocks until the first finishes, then sees the completed file and
# takes the "already exists" fast-path without rebuilding.
_DB_BUILD_LOCK = threading.Lock()

# v2 DB format marker. Any file whose first line does not match this is legacy.
_DB_V2_HEADER = "Plex Music Database v2 (metadata-based)"

# Trailing qualifier parentheticals stripped during normalized matching.
_QUAL_RE = re.compile(
    r'\s*[\(\[]\s*(?:'
    r'(?:\d{4}\s+)?remaster(?:ed)?|'
    r'(?:super\s+)?deluxe(?:\s+edition)?|'
    r'anniversary(?:\s+edition)?|'
    r'(?:(?:bonus\s+tracks?\s+)?edition|bonus\s+tracks?)|'
    r'mono|stereo(?:\s+version)?|'
    r'live(?:\s+version)?|'
    r'explicit|clean|'
    r'single(?:\s+version)?|'
    r'but\s+i\s+like\s+it'      # subtitle of "It's Only Rock 'n' Roll"
    r')\s*[\)\]]\s*$',
    re.IGNORECASE
)

# Track-number prefixes: "01 ", "01 - ", "1-01 ", "2-01 ", "01. "
_TRACK_PREFIX_RE = re.compile(r'^\d+(?:[-.]\d+)?[-. ]+')

# File extension: .mp3, .flac, .m4a, .ogg etc.
_EXT_RE = re.compile(r'\.\w{2,5}$')

# Unicode apostrophe/quote variants normalised to ASCII apostrophe (U+0027).
# U+2019 RIGHT SINGLE QUOTATION MARK is the most common offender: many FLAC
# taggers write "џ\u2019t" while iTunes EXTINF exports plain ASCII "'".
_UNICODE_APOS_RE = re.compile(
    r'[\u2018\u2019\u201A\u201B\u02BC\u0060\u00B4]'
)

# Spaces around ampersand: "Little T & A" <-> "Little T&A".
_AMP_SPACES_RE = re.compile(r'\s*&\s*')


def _ensure_app_dir():
    _APP_DIR.mkdir(parents=True, exist_ok=True)


def _open_m3u(path):
    """Open a .m3u or .m3u8 file, trying UTF-8-sig (handles BOM), then cp1252
    (iTunes Windows export encoding), then UTF-8 with error replacement."""
    for enc in ('utf-8-sig', 'cp1252'):
        try:
            with open(str(path), 'rt', encoding=enc) as f:
                return f.read().splitlines()
        except UnicodeDecodeError:
            continue
    with open(str(path), 'rt', encoding='utf-8', errors='replace') as f:
        return f.read().splitlines()


def _normalize(s: str) -> str:
    """Lowercase and strip trailing qualifier parentheticals.

    Examples:
        'Tattoo You (Remastered)' -> 'tattoo you'
        'Start Me Up (2009 Remaster)' -> 'start me up'
        'Abbey Road (Deluxe Edition)' -> 'abbey road'
    """
    s = s.strip().lower()
    while True:
        stripped = _QUAL_RE.sub('', s).rstrip()
        if stripped == s:
            break
        s = stripped
    # 2. Unicode apostrophe variants -> ASCII apostrophe.
    s = _UNICODE_APOS_RE.sub("'", s)
    # 3. Spaces around ampersand: "t & a" -> "t&a".
    s = _AMP_SPACES_RE.sub('&', s)
    # 4. Abbreviation: "st." -> "street" (e.g. "Exile on Main St.").
    s = re.sub(r'\bst\.(?=\s|$)', 'street', s)
    # 5. Trailing ? and ! (e.g. "Anybody Seen My Baby?").
    s = s.rstrip('?!')
    # 6. Internal commas (e.g. "Have You Seen Your Mother, Baby").
    s = s.replace(',', '')
    # 7. Apostrophes -> space then collapse whitespace.
    #    Handles "rock'n" vs "rock n'" positional variants.
    s = re.sub(r"'", ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def _strip_track_prefix(filename: str) -> str:
    """Strip leading track-number prefix and file extension; return lowercase title stem.

    Examples:
        '01 Start Me Up.mp3'  -> 'start me up'
        '2-01 Rocks Off.mp3'  -> 'rocks off'
        '01 - Slave.flac'     -> 'slave'
        'Come Together.mp3'   -> 'come together'
    """
    s = _EXT_RE.sub('', filename)      # strip extension
    s = _TRACK_PREFIX_RE.sub('', s)    # strip track-number prefix
    return s.strip().lower()


def _parse_extinf(line: str):
    """Parse an EXTINF line into (title, artist).

    iTunes exports as '#EXTINF:<dur>,<Title> - <Artist>' (title first, artist last).
    Splits on the LAST ' - ' to handle hyphens in titles.
    Returns ('', '') if the line cannot be parsed.
    """
    comma = line.find(',')
    if comma == -1:
        return '', ''
    display = line[comma + 1:]
    sep = display.rfind(' - ')
    if sep == -1:
        return display.strip(), ''
    return display[:sep].strip(), display[sep + 3:].strip()


def save_music_database(app, library_name, library_id, song_count, output_file_path=None):
    """Build the Plex music database at %LOCALAPPDATA%\\iTunesToPlex\\Plex Music Database.txt.

    Writes to a .tmp file and os.replace()s on success so an interrupted build
    never leaves a partial file that looks complete.  output_file_path is kept
    for backward-compatibility but is ignored — the path is always DB_PATH.
    """
    with _DB_BUILD_LOCK:
        _ensure_app_dir()

        if os.path.isfile(str(DB_PATH)):
            # Check format: v2 header -> reuse; anything else -> legacy, delete + rebuild.
            try:
                with open(str(DB_PATH), 'r', encoding='utf-8') as chk:
                    header_line = chk.readline().rstrip('\n')
            except OSError:
                header_line = ''

            if header_line == _DB_V2_HEADER:
                app.post_to_status_console(
                    f"Music database already exists at {DB_PATH}, not refreshed.", "info")
                return DB_PATH
            else:
                # Legacy path-based format: delete and fall through to rebuild.
                try:
                    os.remove(str(DB_PATH))
                except OSError:
                    pass
                app.post_to_status_console(
                    "Legacy path-based database found — rebuilding once in new metadata "
                    "format. This may take a minute.", "info")

        tmp_path = DB_PATH.with_suffix('.tmp')
        app.post_to_status_console(f"Creating music database at {DB_PATH}", "info")
        app.create_progressbar("Creating the Music Database", "determinate")

        try:
            with open(str(tmp_path), 'wt', encoding='utf-8') as out:
                out.write(_DB_V2_HEADER + "\n")

                track_count_start = 0
                batch_size = 100
                tracks_written = 0
                index = batch_size   # prime the loop

                while index == batch_size:
                    batch = API_Calls.get_track_data(library_id, track_count_start, batch_size)
                    index = len(batch)
                    for track in batch:
                        try:
                            key = track['ratingKey']
                            artist = track.get('grandparentTitle', '').lower()
                            album  = track.get('parentTitle',      '').lower()
                            title  = track.get('title',            '').lower()
                            out.write("{}:::{}:::{}:::{}\n".format(key, artist, album, title))
                            tracks_written += 1
                        except (KeyError, TypeError) as e:
                            app.post_to_status_console(
                                f"Skipping track with missing metadata ({e})", "warning")

                    track_count_start += batch_size
                    if song_count > 0:
                        pct = min((track_count_start / song_count) * 100, 100)
                        app.update_progressbar(pct)

                if tracks_written == 0:
                    app.post_to_status_console("No tracks found in Music library.", "error")
                    app.close_progressbar()
                    try:
                        tmp_path.unlink()
                    except OSError:
                        pass
                    return None

            # Atomic rename — only reached on full success
            os.replace(str(tmp_path), str(DB_PATH))
            app.post_to_status_console(
                f"Music database created — {tracks_written} tracks written.", "success")

        except Exception as e:
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except OSError:
                pass
            app.post_to_status_console(f"Database build failed: {e}", "error")
            app.close_progressbar()
            raise

        app.close_progressbar()
        return DB_PATH


def find_playlist_keys(app, m3u_playlist, music_database, working_directory):
    """Match tracks in an m3u/m3u8 playlist against the Plex music database.

    music_database  — absolute Path (returned by save_music_database / DB_PATH)
    working_directory — folder containing the m3u file
    """
    db_path = Path(music_database)
    try:
        with open(str(db_path), 'r', encoding='utf-8') as f:
            db_lines = f.read().splitlines()
    except FileNotFoundError:
        raise PlexConnectionError(f"Music database not found: '{db_path}'")
    except Exception as e:
        app.post_to_status_console(f"Error reading database: {e}", "error")
        return []

    # Enforce v2 format — legacy databases cannot be used for metadata-based matching.
    header = db_lines[0] if db_lines else ''
    if header != _DB_V2_HEADER:
        app.post_to_status_console(
            "Legacy path-based database detected — metadata matching not possible. "
            "Use 'Rebuild Music Database' to generate the new format.", "warning")
        return []
    db_lines = db_lines[1:]  # drop header

    # Build exact index: (artist, album, title) -> ratingKey
    # Build fuzzy index: (norm_artist, norm_title) -> [(ratingKey, norm_album)]
    exact_index: dict = {}
    fuzzy_index: dict = {}
    bad_db_lines = 0
    for line in db_lines:
        parts = line.split(':::')
        if len(parts) < 4:
            bad_db_lines += 1
            continue
        try:
            key = int(parts[0])
        except ValueError:
            bad_db_lines += 1
            continue
        db_artist, db_album, db_title = parts[1], parts[2], parts[3]
        exact_index.setdefault((db_artist, db_album, db_title), key)
        na   = _normalize(db_artist)
        nt   = _normalize(db_title)
        nalb = _normalize(db_album)
        fuzzy_index.setdefault((na, nt), []).append((key, nalb))

    if bad_db_lines:
        app.post_to_status_console(
            f"Skipped {bad_db_lines} malformed line(s) in music database.", "warning")

    # Load the m3u/m3u8 playlist with encoding fallback
    m3u_path = working_directory / m3u_playlist
    try:
        m3u_lines = _open_m3u(m3u_path)
    except FileNotFoundError:
        app.post_to_status_console(f"Playlist file not found: '{m3u_path}'", "error")
        return []
    except Exception as e:
        app.post_to_status_console(f"Error reading playlist: {e}", "error")
        return []

    # Detect extended m3u
    has_extinf = any(l.startswith('#EXTINF') for l in m3u_lines)

    # Parse tracks
    playlist_tracks = []
    prev_extinf = None
    for line in m3u_lines:
        if not line:
            continue
        if line.startswith('#EXTINF'):
            prev_extinf = line
            continue
        if line.startswith('#'):
            prev_extinf = None
            continue
        # Path line
        path_parts = line.split('\\') if '\\' in line else line.split('/')
        if len(path_parts) < 2:
            prev_extinf = None
            continue

        album = path_parts[-2].lower()

        if has_extinf and prev_extinf is not None:
            extinf_title, extinf_artist = _parse_extinf(prev_extinf)
            artist = extinf_artist.lower()
            title  = extinf_title.lower()
        else:
            artist = path_parts[-3].lower() if len(path_parts) >= 3 else ''
            title  = _strip_track_prefix(path_parts[-1])

        playlist_tracks.append({'artist': artist, 'album': album, 'title': title})
        prev_extinf = None

    # Two-pass lookup
    key_list    = []
    exact_count = 0
    fuzzy_count = 0
    for track in playlist_tracks:
        artist = track['artist']
        album  = track['album']
        title  = track['title']

        # Pass 1: exact match
        key = exact_index.get((artist, album, title))
        if key is not None:
            key_list.append(key)
            exact_count += 1
            continue

        # Pass 2: normalized match
        na     = _normalize(artist)
        nt     = _normalize(title)
        na_alb = _normalize(album)
        candidates = fuzzy_index.get((na, nt), [])

        matched_key = None
        for cand_key, cand_alb in candidates:
            if not na_alb or not cand_alb or na_alb in cand_alb or cand_alb in na_alb:
                matched_key = cand_key
                break

        # If album substring check failed for every candidate, use the first one
        # regardless of album. Handles cross-album / compilation mismatches where
        # the m3u album name does not match any DB album for this artist+title.
        if matched_key is None and candidates:
            matched_key = candidates[0][0]

        if matched_key is not None:
            key_list.append(matched_key)
            fuzzy_count += 1
        else:
            app.post_to_status_console(
                f"Not found — Track: {title}  Album: {album}  Artist: {artist}",
                "warning")

    total = len(playlist_tracks)
    found = len(key_list)
    if found > 0:
        summary = (
            f"Of the {total} tracks in the playlist, {found} were found on the "
            f"Plex server ({exact_count} exact, {fuzzy_count} fuzzy)."
        )
    else:
        summary = (
            f"Of the {total} tracks in the playlist, 0 were found on the Plex server."
        )
    app.post_to_status_console(summary, "info")
    return key_list
