# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ultimation LLC and Robert C Suffern
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import os
from pathlib import Path

import API_Calls
from API_Calls import PlexConnectionError

# Fixed storage location: %LOCALAPPDATA%\iTunesToPlex\Plex Music Database.txt
_APP_DIR = Path(os.getenv("LOCALAPPDATA", "")) / "iTunesToPlex"
if not str(_APP_DIR).strip("/\\"):
    # LOCALAPPDATA not set (non-Windows fallback)
    _APP_DIR = Path.home() / "AppData" / "Local" / "iTunesToPlex"

DB_PATH = _APP_DIR / "Plex Music Database.txt"


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


def save_music_database(app, libray_name, library_id, song_count, output_file_path=None):
    """Build the Plex music database at %LOCALAPPDATA%\\iTunesToPlex\\Plex Music Database.txt.

    Writes to a .tmp file and os.replace()s on success so an interrupted build
    never leaves a partial file that looks complete.  output_file_path is kept
    for backward-compatibility but is ignored — the path is always DB_PATH.
    """
    _ensure_app_dir()

    if os.path.isfile(str(DB_PATH)):
        app.post_to_status_console(
            f"Music database already exists at {DB_PATH}, not refreshed.", "info")
        return DB_PATH

    tmp_path = DB_PATH.with_suffix('.tmp')
    app.post_to_status_console(f"Creating music database at {DB_PATH}", "info")
    app.create_progressbar("Creating the Music Database", "determinate")

    try:
        with open(str(tmp_path), 'wt', encoding='utf-8') as out:
            # Fetch the first track to derive the common path prefix
            first_batch = API_Calls.get_track_data(library_id, 0, 1)
            if not first_batch:
                app.post_to_status_console("No tracks found in Music library.", "error")
                app.close_progressbar()
                return None

            first_track = first_batch[0]
            first_path = first_track['Media'][0]['Part'][0]['file']
            position = first_path.find(libray_name + "/") + len(libray_name) + 1
            common_path = first_path[:position]
            out.write("The Plex path for Music is: " + common_path + "\n")

            track_count_start = 0
            batch_size = 100
            tracks_written = 0
            index = batch_size   # prime the loop

            while index == batch_size:
                batch = API_Calls.get_track_data(library_id, track_count_start, batch_size)
                index = len(batch)   # loop continues only while API returns a full batch
                for track in batch:
                    try:
                        key = track['ratingKey']
                        file_path = track['Media'][0]['Part'][0]['file']
                        relative = file_path[position:]
                        parts = relative.split("/")
                        depth = len(parts)
                        if depth >= 3:
                            artist, album, title = parts[-3].lower(), parts[-2].lower(), parts[-1].lower()
                        elif depth == 2:
                            # artist/track.flac — no album subfolder
                            artist, album, title = parts[-2].lower(), "", parts[-1].lower()
                        else:
                            app.post_to_status_console(
                                f"Skipping track — unrecognisable path: {relative}", "warning")
                            continue
                        out.write("{}:::{}:::{}:::{}\n".format(key, artist, album, title))
                        tracks_written += 1
                    except (IndexError, KeyError) as e:
                        app.post_to_status_console(
                            f"Skipping track with missing metadata ({e})", "warning")

                track_count_start += batch_size
                if song_count > 0:
                    pct = min((track_count_start / song_count) * 100, 100)
                    app.update_progressbar(pct)

        # Atomic rename — only reached on full success
        os.replace(str(tmp_path), str(DB_PATH))
        app.post_to_status_console(
            f"Music database created — {tracks_written} tracks written.", "success")

    except Exception as e:
        # Clean up temp file so a future run starts fresh
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

    if db_lines:
        db_lines.pop(0)   # strip header line

    # Build lookup dict: (artist, album, track) -> ratingKey
    # dict.setdefault keeps the FIRST entry on duplicates, preserving prior behaviour.
    music_db = {}
    bad_db_lines = 0
    for line in db_lines:
        parts = line.split(":::")
        if len(parts) < 4:
            bad_db_lines += 1
            continue
        try:
            key = int(parts[0])
        except ValueError:
            bad_db_lines += 1
            continue
        music_db.setdefault((parts[1], parts[2], parts[3]), key)
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

    playlist_db = []
    for line in m3u_lines:
        if not line or line.startswith("#"):
            continue
        # Try backslash split (Windows paths), fall back to forward slash
        parts = line.split("\\")
        if len(parts) < 3:
            parts = line.split("/")
        if len(parts) < 3:
            continue
        playlist_db.append({
            'Artist': parts[-3].lower(),
            'Album': parts[-2].lower(),
            'Track': parts[-1].lower(),
        })

    # O(1) lookup per playlist track
    key_list = []
    for playlist_track in playlist_db:
        lookup_key = (playlist_track['Artist'], playlist_track['Album'], playlist_track['Track'])
        rating_key = music_db.get(lookup_key)
        if rating_key is not None:
            key_list.append(rating_key)
        else:
            app.post_to_status_console(
                f"Not found — Track: {playlist_track['Track']}  "
                f"Album: {playlist_track['Album']}  "
                f"Artist: {playlist_track['Artist']}", "warning")

    app.post_to_status_console(
        f"Of the {len(playlist_db)} tracks in the playlist, "
        f"{len(key_list)} were found on the Plex server.", "info")
    return key_list
