# Claude Code Prompts — Round 2 (iTunes Playlist Import to Plex)

Round 1 (Prompts 1-5, branch `fix/audit-round-1`, HEAD `eed9f2d`) covered the
Top 5 audit actions: credential leaks, hard-exit/`len(False)` crashes, the
central HTTP layer + stale `lru_cache`, background threading, and the music
database lifecycle.

This round covers the next tier of findings from `audit-report.md` that
weren't addressed yet. Same rules as Round 1: run these one at a time, in
order, each as its own commit, and test manually before moving on.

## Kickoff for this round

```
Round 1 is done and merged/in review (branch fix/audit-round-1, HEAD eed9f2d).
Starting Round 2: create and switch to a new branch fix/audit-round-2 off the
current HEAD. Then work through the 5 prompts below ONE AT A TIME, in order.
After each one: make a separate commit with a clear message, tell me exactly
what changed and which files, and wait for me to confirm testing passed
before starting the next prompt. If a fix references a line number that has
shifted because of an earlier fix (in this round or Round 1), find the
equivalent code by description rather than by line number.
```

---

## Prompt 1 — Library picker (stop hardcoding "Music")

```
Audit finding: Plex_Playlist_Import_Main.py hardcodes the target library name
as "Music" in two places:
1. import_playlist_to_plex() sets target_library = "Music" and matches it
   against section_info[i]['Title'].
2. rebuild_plex_database() checks `if section['Title'] == "Music":`.

This breaks for anyone whose Plex music library isn't named exactly "Music"
(e.g. "Music Library", "Tunes", a second music library for a shared server).

Fix:
1. In Screen_Manager.py, add a ttk.Combobox (label "Target Music Library:")
   on the Import page, near the M3U folder browser. Store the selection on
   the app instance as `self.selected_library` (a StringVar), defaulting to
   "" until populated.
2. After a successful login (in initialize_screen_data, or right after
   get_plex_information() is called in ip_login_process/plex_login_process),
   populate the combobox with the titles of all sections whose 'Type' is
   'artist' (Plex's section type for music libraries — see
   get_plex_information()'s section_info list, which has 'Type' and 'Title'
   keys). If exactly one music library is found, select it automatically. If
   none are found, leave it empty and post a status console warning. If more
   than one is found, default to one named "Music" if present, else the
   first one, and let the user change it.
3. In Plex_Playlist_Import_Main.py, replace the hardcoded "Music" in
   import_playlist_to_plex() and rebuild_plex_database() with
   app.selected_library.get() (or equivalent). If it's empty, post a status
   console error ("No music library selected — check the Login/Info tabs and
   try again") and return early instead of failing on a "library not found"
   message.

Verify: log in to a server with at least one music library — confirm the
dropdown shows it (auto-selected if it's the only one). If you have access to
a server with a music library NOT named "Music", confirm selecting it makes
import/rebuild target that library instead of failing with "Target library
not found".
```

---

## Prompt 2 — Confirm before deleting or replacing a Plex playlist

```
Audit finding: two places silently delete playlists on the Plex server with
no confirmation:
1. delete_plex_playlists() in Plex_Playlist_Import_Main.py deletes every
   playlist selected in the "Plex Playlists" listbox immediately on click.
2. import_playlist_to_plex() silently deletes an existing Plex playlist with
   the same name as the one being imported (so it can recreate it), with no
   warning to the user.

Fix:
1. delete_plex_playlists() is currently called directly from a button
   command in Screen_Manager.py (not via _run_in_thread, so it's already on
   the main thread). Before calling API_Calls.delete_playlist() for the
   selected playlists, show a single messagebox.askyesno() listing the
   playlist name(s) that will be deleted (e.g. "Delete the following
   playlist(s) from Plex?\n\n- Workout Mix\n- Road Trip"). If the user clicks
   No, abort with no changes and post a status console message ("Delete
   cancelled.").
2. For import overwrite: messagebox calls must happen on the main thread, but
   import_playlist_to_plex() runs in a background thread via _run_in_thread.
   So do this check BEFORE starting the thread: in the "Import to Plex"
   button's command (Screen_Manager.py), call API_Calls.get_playlists() on
   the main thread to get existing Plex playlist titles, compare against the
   names of the selected M3U files (same .m3u/.m3u8 stripping logic used in
   import_playlist_to_plex), and if any selected playlist would overwrite an
   existing one, show a single messagebox.askyesno() listing them (e.g.
   "These playlists already exist on Plex and will be replaced:\n\n- Workout
   Mix\n\nContinue?"). If No, don't start the import thread at all. If Yes
   (or nothing would be overwritten), proceed with _run_in_thread as before.

Verify: (a) select one or more playlists in the "Plex Playlists" list, click
"Delete Playlist(s)" — confirm a Yes/No dialog lists them; clicking No leaves
them untouched, clicking Yes deletes them as before. (b) Import an .m3u file
whose name matches an existing Plex playlist — confirm a Yes/No dialog
appears before anything is deleted/recreated; clicking No leaves the existing
playlist untouched and does not start an import.
```

---

## Prompt 3 — Replace `print()` with `logging`

```
Audit follow-up: ~50 print() calls remain across API_Calls.py, Plex_Login.py,
Plex_Playlist_Import_Main.py, and Screen_Manager.py. These are invisible if
the app is ever built with --windowed, and aren't persisted anywhere.

Fix:
1. In main.py, configure logging at startup:
   - Log directory: %LOCALAPPDATA%\iTunesToPlex\logs (create if missing,
     same pattern as Music_Database_Import.py's _APP_DIR).
   - A RotatingFileHandler writing to logs\app.log (maxBytes=1_000_000,
     backupCount=3, encoding="utf-8") AND a StreamHandler (so the console
     window from build.bat still shows live output).
   - Format: "%(asctime)s %(levelname)s %(name)s: %(message)s", level INFO.
2. In each of the four files above, add `import logging` and
   `logger = logging.getLogger(__name__)` near the top, then replace every
   print(...) with an appropriately-leveled logger call:
   - Routine progress/status ("Attempting IP address...", "Processing
     playlist...") -> logger.info(...)
   - Recoverable problems ("No files selected", "Plex at {ip} failed") ->
     logger.warning(...)
   - Caught exceptions / failures -> logger.error(...)
   - Debugging-only noise (e.g. raw response dumps, the photo_count counter
     in library_regression) -> logger.debug(...)
3. Double-check none of these log statements include a password or
   globals.PLEX_TOKEN value (Round 1 already removed the worst offenders, but
   re-check anything that logs full URLs or headers — with the header-based
   auth from Round 1 this should be clean, but verify).
4. post_to_status_console() in Screen_Manager.py is for the GUI console and
   should stay as-is, but consider also calling logger.info/warning/error
   from inside it (matching the tag) so GUI status messages are also captured
   in the log file for later debugging.

Verify: run the built .exe, perform a login and an import. Confirm the
console window shows readable timestamped log lines (not bare prints), and
that %LOCALAPPDATA%\iTunesToPlex\logs\app.log exists and contains the same
information. Search the log file for "password" and the literal token value
— confirm neither appears.
```

---

## Prompt 4 — App icon and version info for the .exe

```
Audit follow-up: the built .exe (dist\ItunesToPlex\ItunesToPlex\ItunesToPlex.exe)
uses the default PyInstaller icon and has no version metadata (no Properties
> Details tab info), which looks unfinished/untrustworthy to end users like a
non-technical family member.

Fix:
1. If there's no existing icon.ico in the repo, generate a simple one: write
   a small one-off script using Pillow (add Pillow to a new
   requirements-dev.txt if not already a dependency — it's only needed at
   build time, not runtime) that creates a basic 256x256 icon (e.g. a
   stylized music note or "P -> Plex" arrow on a solid background) and saves
   it as icon.ico with multiple sizes (16, 32, 48, 256). Keep it simple —
   this is a placeholder that can be swapped later.
2. Create version_info.txt in the repo root, a PyInstaller version-resource
   file (the format produced by `pyi-grab_version` / used with
   --version-file). Set: CompanyName "Ultimation LLC", FileDescription
   "iTunes Playlist Import to Plex", ProductName "iTunes Playlist Import to
   Plex", FileVersion and ProductVersion to 1.0.0.0 (or derive from the most
   recent git tag if one exists, else 1.0.0.0), and a copyright string
   matching the SPDX header already in the source files.
3. Update build.bat to add `--icon=icon.ico` and
   `--version-file=version_info.txt` to the PyInstaller command.
4. Add icon.ico and version_info.txt to git (don't gitignore them).

Verify: run build.bat, then in File Explorer check that
dist\ItunesToPlex\ItunesToPlex\ItunesToPlex.exe shows the new icon (not the
default PyInstaller one). Right-click the .exe -> Properties -> Details tab
-> confirm Product name, File version, and Company name are populated.
```

---

## Prompt 5 — Faster playlist matching + a pytest suite

```
Audit follow-ups, both touching Music_Database_Import.py:

1. find_playlist_keys() matches each playlist track against the music
   database with a nested loop (for each of N playlist tracks, scan up to M
   database tracks comparing artist/album/track) — O(N*M). For large
   libraries (10k+ tracks) and big playlists this is slow.

2. There's no automated test coverage for find_playlist_keys() (encoding
   fallback, malformed db lines, 2-level vs 3-level paths) or for the
   API_Calls.py HTTP layer (_request, add_songs_to_Plex_playlist batching).

Fix:
1. In find_playlist_keys(), after building music_db_list, build a lookup dict
   keyed by (Artist, Album, Track) -> Key using dict.setdefault() (so the
   FIRST matching db entry wins, preserving current behavior on duplicates).
   Replace the nested-loop match with a single dict.get() per playlist track,
   keeping the existing "not found" warning message for misses. Confirm the
   "Of the X tracks in the playlist, Y were found" summary is unchanged.
2. Add a tests/ directory with:
   - tests/test_music_database_import.py: build small in-memory/temp-file
     fixtures for a music database (a few ::: -delimited lines, including one
     malformed line and one with an artist/track containing accented
     characters) and an .m3u playlist (one UTF-8, one cp1252-encoded with an
     accented filename). Test that find_playlist_keys() returns the expected
     ratingKeys, skips the malformed db line with a warning (not a crash),
     and handles both encodings.
   - tests/test_api_calls.py: use the `responses` library to mock HTTP calls
     for add_songs_to_Plex_playlist() (verify it batches in groups of 50 and
     returns (song_count, return_size) correctly) and for _request() (verify
     a non-2xx response raises PlexAPIError, and a connection error also
     raises PlexAPIError rather than the raw requests exception).
3. Add pytest and responses to requirements-dev.txt (create it if Prompt 4
   didn't already).

Verify: run `pytest` from the repo root — all tests pass. Then do a real
import of a moderately-sized playlist (20+ songs) against your normal
library and confirm the match results (count found / not found) are
identical to before this change.
```

---

## Optional follow-ups (lower priority — do after the above are stable)

- **Plex.tv login error detail / 2FA note**: `plex_login()`'s `except
  Exception as e: return False` (Plex_Login.py) swallows the actual error.
  Differentiate at least: HTTP 401 (bad username/password — and note that
  Plex's legacy `sign_in.json` endpoint doesn't support accounts with 2FA
  enabled, so suggest Method 2 in that case) vs. network/timeout errors, and
  post a more specific status console message for each.
- **IP/token field validation**: the IP Address and Token Entry fields
  (Method 2) have no input validation, unlike the Request Timeout field which
  already uses `validate_digits`. Add a basic IPv4-format check on the IP
  field (visual feedback, e.g. red border, on invalid input) before
  attempting to connect.
- **UI polish**: set a `self.minsize(...)` so the window can't be resized
  small enough to break the layout; add placeholder/greyed example text to
  the IP Address and Token fields (e.g. "192.168.1.100"); make the Plex port
  (currently fixed at `globals.PLEX_PORT = 32400`) an editable field for
  users running Plex on a non-default port.
- **Code cleanup**: remove the dead/commented-out code in
  `library_regression()` and `get_photo_library_count()`
  (Plex_Playlist_Import_Main.py), fix the `libray_name` parameter typo
  throughout Music_Database_Import.py, and consider refactoring the three
  bare globals in globals.py (PLEX_IP_ADDRESS, PLEX_PORT, PLEX_TOKEN) into a
  small connection-state object passed around explicitly — this is a bigger,
  cross-file change so do it last and on its own branch.

---

## Testing after each fix

Same setup as Round 1: after Claude Code says a fix is ready, run
`build.bat`, then run `dist\ItunesToPlex\ItunesToPlex\ItunesToPlex.exe`, with
the console window visible.

### After Prompt 1 — Library picker
- Log in to your Plex server. Go to the Import tab — confirm a "Target Music
  Library" dropdown appears, pre-populated (auto-selected if you only have
  one music library).
- Import a playlist and confirm it still works exactly as before.
- **Pass:** dropdown appears and is populated after login; import still works
  with the (auto-)selected library.

### After Prompt 2 — Delete/overwrite confirmation
- In the "Plex Playlists" list, select one and click "Delete Playlist(s)".
  Confirm a Yes/No dialog names it. Click **No** — confirm it's still listed
  afterward (not deleted). Click the button again and choose **Yes** —
  confirm it's now gone.
- Import an .m3u file whose name matches an existing Plex playlist. Confirm a
  Yes/No dialog appears before anything happens. Click **No** — confirm the
  existing playlist is untouched and no import ran. Re-run and click **Yes**
  — confirm it imports as before (old playlist replaced).
- **Pass:** both deletes and import-overwrites require explicit confirmation;
  declining leaves Plex unchanged.

### After Prompt 3 — Logging
- Perform a login and an import. Confirm the console window shows readable,
  timestamped log lines.
- Open `%LOCALAPPDATA%\iTunesToPlex\logs\app.log` — confirm it exists and
  contains the same session's activity.
- **Pass:** console and log file both show activity; neither contains your
  password or the literal Plex token value.

### After Prompt 4 — Icon and version info
- After building, check the .exe's icon in File Explorer — should no longer
  be the default PyInstaller icon.
- Right-click the .exe -> Properties -> Details — confirm Product name, File
  version, and Company name are filled in.
- **Pass:** custom icon shows in Explorer; version info populated in
  Properties.

### After Prompt 5 — Faster matching + tests
- Run `pytest` from the repo root — confirm all tests pass.
- Re-import a playlist you've imported before (ideally a larger one) and
  confirm the "X of Y songs added" result matches what you got previously.
- **Pass:** `pytest` is green; import results unchanged from before the
  optimization.
