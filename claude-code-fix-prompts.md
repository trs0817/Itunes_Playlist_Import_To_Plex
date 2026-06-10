# Claude Code Fix Prompts — iTunes Playlist Import to Plex

Run these one at a time, in order, from inside the project folder (the actual repo checkout, not a zip extract — see git note at the bottom). Each is scoped to be its own commit/PR. Test the app manually after each before moving to the next.

---

## Prompt 1 — Stop leaking credentials (Critical security)

```
Audit finding: Plex_Login.py and API_Calls.py print the user's Plex.tv password and
auth token to stdout, the password Entry field doesn't mask input, and the
Server Information tab displays the raw token.

Fix all of the following in this repo:
1. Plex_Login.py: remove the print() that includes the password (around line 45)
   and every print() that includes globals.PLEX_TOKEN (lines ~56, 122, 138, 151).
2. API_Calls.py: remove the print() at line ~28 that includes the token.
3. Screen_Manager.py: add show="*" to the password Entry widget (~line 159) so
   the Plex.tv password is masked as typed.
4. Plex_Playlist_Import_Main.py (~line 117): remove the ('Token', globals.PLEX_TOKEN)
   row from the Server Information listbox, or replace it with a masked value
   like '****' plus a "Copy Token" button that copies the real value to the
   clipboard without displaying it.
5. Plex_Login.py: in plex_login() and ip_login(), stop sending X-Plex-Token as a
   URL query parameter (~lines 121, 150, 153). Use the X-Plex-Token header
   instead, matching the pattern already used in API_Calls.py's get_globals().

Do not remove any error-reporting that doesn't involve credentials/tokens —
only the lines that print secrets. After the change, confirm with grep that
no print()/log statement anywhere in the repo includes 'password' or
'PLEX_TOKEN'.
```

---

## Prompt 2 — Fix hard exits and the `len(False)` crash (Critical robustness)

```
Audit findings:
- API_Calls.py (~line 35) and Music_Database_Import.py (~line 79) call exit(...)
  on errors, which kills the entire Tkinter app with no chance for the GUI to
  show a message.
- Music_Database_Import.py's find_playlist_keys() returns False on file errors
  (lines ~82, 101, 104), but Plex_Playlist_Import_Main.py (~lines 221-222)
  immediately calls len(playlist_keys) on the result, which raises
  TypeError: object of type 'bool' has no len() when it's False.

Fix:
1. Replace both exit(...) calls with raising a custom exception (e.g.
   PlexConnectionError(Exception)). Catch this exception at the call sites in
   Screen_Manager.py / Plex_Playlist_Import_Main.py and report the error via
   app.post_to_status_console(..., "error") instead of crashing.
2. Change find_playlist_keys() to return [] instead of False on all error
   paths, and add an `if not playlist_keys:` guard before any len()/iteration
   on it in Plex_Playlist_Import_Main.py, posting a status message when empty.
3. Add a global Tkinter exception handler in main.py / Screen_Manager.py via
   `app.report_callback_exception = ...` that catches any remaining unhandled
   exceptions in Tk callbacks, logs them, and shows a status console error
   instead of silently failing or crashing.

Verify by simulating a failure (e.g. point the app at an unreachable IP, and
a missing/corrupt m3u file) and confirming the app stays open and shows a
clear error message in the status console both times.
```

---

## Prompt 3 — Central HTTP layer + fix the stale lru_cache (High robustness)

```
Audit findings:
- Most functions in API_Calls.py make raw requests.get/post/put/delete calls
  with no timeout, no raise_for_status(), and assume response.json() always
  succeeds and contains expected keys (e.g. data["MediaContainer"]["Metadata"]).
- Plex_Playlist_Import_Main.py decorates get_plex_information() and
  get_photo_library_count() with @lru_cache, so after a user reconnects to a
  different Plex server (or rebuilds libraries), stale cached server info /
  library keys are reused silently, causing imports to target the wrong server.
- API_Calls.py functions like search_for_song (~line 144) and others
  (~lines 133, 194; Plex_Playlist_Import_Main.py ~239) build URLs by string
  concatenation without encoding dynamic values (song titles, playlist names),
  so names containing & or # break the request.

Fix:
1. In API_Calls.py, create a small shared helper (e.g. a module-level
   requests.Session with a default timeout, e.g. 10 seconds, and a
   `_request(method, url, **kwargs)` wrapper that calls raise_for_status()
   and catches requests.exceptions.RequestException, raising a single
   PlexAPIError with a user-friendly message). Route all existing
   requests.get/post/put/delete calls in this file through it.
2. Remove the @lru_cache decorators from get_plex_information() and
   get_photo_library_count() in Plex_Playlist_Import_Main.py. Instead, fetch
   this info once after a successful login/reconnect and store it as an
   instance attribute on `app` (or a small connection-state object), so it's
   refreshed every time the user reconnects.
3. Replace all string-concatenated URL parameters that include user/file-derived
   text (song titles, playlist names) with urllib.parse.quote() or requests'
   `params=` dict, so special characters like & # ? don't break requests.
4. search_for_song should return None (not a raw Response object) when no
   match is found, for consistency with other lookup functions — update all
   call sites accordingly.

Verify: a playlist or song containing '&' imports correctly, an unreachable
server produces a clean status-console error (not a stack trace), and
reconnecting to a second Plex server updates the Server Information tab.
```

---

## Prompt 4 — Move long operations off the UI thread (High performance)

```
Audit finding: the LAN IP scan (Plex_Login.py), the music database build
(Music_Database_Import.py), and the playlist import (Plex_Playlist_Import_Main.py)
all run on Tkinter's main thread. The UI freezes during these, and any
top.update() calls used to keep it responsive also allow re-entrancy — e.g.
the user can click "Import" again while an import is already running.

Fix:
1. Wrap the IP scan, database build, and playlist import operations in
   threading.Thread (daemon=True), started from their respective button
   callbacks in Screen_Manager.py.
2. Disable the triggering button(s) for the duration of the operation, and
   re-enable them when it completes (success or error). Use app.after(0, ...)
   to marshal any UI updates (status console messages, progress, re-enabling
   buttons) back onto the main thread from the worker thread — do not touch
   Tkinter widgets directly from the background thread.
3. Remove any direct top.update()/update_idletasks() calls that were being
   used as a workaround for blocking the UI during these operations, since
   they're no longer needed once the work is on a background thread.
4. Add a protocol("WM_DELETE_WINDOW", ...) handler in Screen_Manager.py /
   main.py that, if a worker thread is running when the window is closed,
   either waits briefly for it to finish or warns the user before exiting.

Verify: start a database rebuild on a large library, confirm the UI remains
responsive (window can be moved/resized, status console updates live), the
Import button is disabled until it finishes, and clicking it again mid-run
does nothing.
```

---

## Prompt 5 — Fix the music database lifecycle (High robustness/usability)

```
Audit findings about Music_Database_Import.py and the "Plex Music Database.txt"
file it builds:
1. It's opened without a context manager and stays open on exception; if the
   build is interrupted partway, a partial file remains and is treated as
   complete forever after (os.path.isfile check).
2. m3u and database files are read/written assuming UTF-8. iTunes for Windows
   exports .m3u files in cp1252 (ANSI), so any accented artist/title raises
   UnicodeDecodeError.
3. Per-track parsing assumes every track has Media[0].Part[0].file and a
   3-level artist/album/title path; tracks at the library root or with
   missing media raise IndexError, and song_count == 0 causes a
   ZeroDivisionError in the percent-complete calculation.
4. The database file is written into the user's m3u/music folder rather than
   an app data directory, and the only way to refresh it is for the user to
   manually find and delete the file (per the README).
5. DB lines are parsed with int(music_list[0]) and fixed indexing with no
   validation, so a corrupted/truncated line raises ValueError/IndexError.

Fix:
1. Use `with open(...)` everywhere this file is read or written. Build it in a
   temp file and os.replace() it into place only on success, so an
   interrupted build never leaves a file that's mistaken for complete.
2. When reading .m3u files, try UTF-8 first and fall back to cp1252 on
   UnicodeDecodeError (or open with errors="replace" as a last resort). Also
   accept .m3u8 extensions.
3. Wrap each track's metadata extraction in try/except, skip and log
   (post_to_status_console "warning") any track that doesn't match the
   expected structure instead of crashing. Guard the percent-complete
   calculation against song_count == 0.
4. Move the database file to %LOCALAPPDATA%\iTunesToPlex\Plex Music Database.txt
   (use os.getenv("LOCALAPPDATA")), creating the directory if needed. Update
   any code/README references to its location.
5. Add a "Rebuild Music Database" button in Screen_Manager.py that deletes the
   existing database file and re-triggers the build (on a background thread,
   per Prompt 4). When parsing the database, validate each line's shape
   (correct number of ::: separated fields, first field is an int) and skip
   malformed lines with a warning instead of raising.

Verify: build the database against a library containing at least one track
with a non-ASCII artist/title and one track at the library root with
non-standard metadata — the build completes without crashing, skipped tracks
are logged, and the database is created under %LOCALAPPDATA%.
```

---

## Optional follow-ups (lower priority, do after the above are stable)

- Replace the ~50 `print()` calls with the `logging` module (rotating file
  handler under `%LOCALAPPDATA%\iTunesToPlex\logs\`, redacting any token
  values).
- Add a target-library dropdown (Plex_Playlist_Import_Main.py currently
  hardcodes `"Music"`).
- Add a `requirements.txt` pinning `requests>=2.32.4` and current `plexapi`.
- Add a confirmation dialog before deleting/replacing an existing Plex
  playlist with the same name.
- Add a basic pytest suite for `find_playlist_keys` (UTF-8/cp1252 fixtures,
  malformed lines) and a `responses`-mocked test for
  `add_songs_to_Plex_playlist`.

---

## About pushing changes to GitHub

The folder you have is an extracted zip of the repo (no `.git` directory), so
there's no git history or remote to push to yet. To get fixes back into
Robert's GitHub repo, the standard flow is:

1. **If you have collaborator/push access to Robert's repo:** clone it fresh
   with `git clone <repo-url>`, work in a new branch (e.g.
   `git checkout -b fix/security-and-crashes`), commit each fix as you go,
   then `git push origin fix/security-and-crashes` and open a Pull Request on
   GitHub. Robert reviews and merges it — yes, he decides whether/when to
   merge into `main`/`master`.

2. **If you don't have push access:** click "Fork" on the GitHub repo page to
   create your own copy under your account, clone *your fork*, make the same
   branch/commit/push as above, then open a Pull Request from your fork's
   branch into Robert's repo. He still reviews and merges (or not).

Either way, your local commits never land in his repo automatically — a push
only updates the remote you're pushing to (your fork or, if you're a
collaborator, a branch on his repo), and merging into the default branch is
a separate, deliberate step Robert takes (via the PR "Merge" button, or his
own `git merge`/`git pull`).

If you tell me the repo URL and whether you're a collaborator, I can walk you
through the exact `git` commands for your situation.
