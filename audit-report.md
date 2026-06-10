# Audit Report — iTunes Playlist Import to Plex
**Date:** 2026-06-09 | **Scope:** main.py, globals.py, Screen_Manager.py, Plex_Login.py, API_Calls.py, Music_Database_Import.py, Plex_Playlist_Import_Main.py, README.md (v1.0, master branch)

**Note on audit scope:** The audit brief assumes `Music_Database_Import.py` uses SQLite. It does not — the "music database" is a flat text file (`Plex Music Database.txt`) with `:::` delimiters, written to the user's m3u folder. There is no SQL anywhere in the codebase, so SQL injection is not applicable; findings below address the text-file approach instead.

---

## 1. Security
| Severity | File:Line | Issue | Recommendation |
|---|---|---|---|
| **Critical** | Plex_Login.py:45 | `print(f"Attempting login with username: {username} and password: {password}")` writes the user's Plex.tv password in plaintext to stdout. | Delete the line. Never log credentials at any level. |
| **Critical** | Plex_Login.py:56, 122, 138, 151; API_Calls.py:28 | Auth token printed to console repeatedly, including full URLs containing `?X-Plex-Token=...`. In a packaged .exe these can end up in captured stdout/logs. | Remove all token prints; if a URL must be logged, redact the token (`X-Plex-Token=***`). |
| **High** | Screen_Manager.py:159 | Password Entry widget has no `show="*"` — the Plex password is displayed in cleartext on screen as typed. | `tk.Entry(..., show="*")`. |
| **High** | Plex_Login.py:121, 150, 153 | Token sent as URL query parameter during server probing. Query strings leak into proxy logs, packet captures, and any logging middleware. The rest of the app correctly uses the `X-Plex-Token` header (API_Calls.py:16). | Use the header form in `plex_login()` and `ip_login()` too. |
| **Medium** | Plex_Playlist_Import_Main.py:117 | The token is added to the Server Information tab (`('Token', globals.PLEX_TOKEN)`) and rendered in a visible listbox — exposed to shoulder-surfing and screenshots. | Drop the row or display a masked value with a "copy" button. |
| **Medium** | Plex_Login.py:28 | Login uses the legacy `plex.tv/users/sign_in.json` endpoint and sends the raw password. No 2FA support — accounts with 2FA enabled will fail with a confusing error. | Migrate to Plex's PIN-based OAuth flow (`/api/v2/pins`); the app never needs to touch the password. |
| **Medium** | API_Calls.py:133, 194; Plex_Playlist_Import_Main.py:239 | User/file-derived strings (song title, playlist name) concatenated into URLs unencoded. A playlist named `Rock & Roll #1` injects `&`/`#` into the query string, silently truncating or altering the request. | Use `requests` `params={}` or `urllib.parse.quote()` for all dynamic URL components. |
| **Medium** | Screen_Manager.py:192–198; Plex_Login.py:146–153 | No validation of IP/token fields. Arbitrary text is interpolated directly into the request URL (e.g. `ip = "evil.com/x?"` changes the request target). | Validate IP with `ipaddress.ip_address()`; validate token charset (`[A-Za-z0-9_-]+`) before use. |
| **Low** | README.md:13; Plex_Login.py:121,150 | All server traffic is plain `http://`. Acceptable on a trusted home LAN, but on shared/untrusted networks the token and library data transit in cleartext. | Document the risk in README; optionally attempt `https://` first and fall back to `http://`. |
| **Low** | (repo root) | No `requirements.txt` / pinned dependencies, so CVE exposure is whatever the build machine had. `requests` < 2.31.0 has CVE-2023-32681 (Proxy-Authorization leak) and < 2.32.x has CVE-2024-35195 (cert-verification bypass). | Add a pinned `requirements.txt` (`requests>=2.32.4`, current `plexapi`, `xmltodict`) and run `pip-audit` before each release. |
| **Info** | globals.py:8–10 | Positive: token/credentials are held in memory only and never persisted to disk between runs. | Keep it that way; if persistence is added later, use Windows Credential Manager (`keyring`). |

## 2. Usability
| Severity | File:Line | Issue | Recommendation |
|---|---|---|---|
| **High** | Plex_Playlist_Import_Main.py:194 | Target library is hardcoded to `"Music"`. Anyone whose music library has a different name gets "Target library:Music not found" with no remedy. | Populate a dropdown from `get_library_sections()` filtered to `type == "artist"`. |
| **High** | Music_Database_Import.py:16–19; README.md:25 | Library cache staleness is handled by telling users to manually find and delete `Plex Music Database.txt`. The UI never shows where it lives or when it was built. | Add a "Rebuild Music Database" button; show DB age and warn when DB track count ≠ current library count. |
| **Medium** | Screen_Manager.py:216–218 | `validate_digits` is a `@staticmethod` declared with `(self, value)`. Tk's `%P` callback passes one argument, so the callback errors and Tcl silently disables validation — the timeout field accepts any text, which later crashes the login loop (Plex_Login.py:125 `float(...)` ValueError). | Remove the `@staticmethod` decorator (or drop `self`). Add a try/except around the `float()` conversion. |
| **Medium** | Plex_Login.py:59–61 | A Plex.tv login failure is swallowed (`except Exception: return False`); the user gets only a generic "check credentials" message even when the real cause is no network, 2FA, or rate-limiting. | Distinguish auth failure (401) from network failure and say which in the status console. |
| **Medium** | Screen_Manager.py:152–198 | No placeholder/hint text in username, password, IP, or token fields; the only guidance is dense italic paragraphs. Port is not editable at all (fixed 32400 in globals.py:9). | Add placeholder hints (`xxx.xxx.xxx.xxx`), an editable port field, and shorten the help text. |
| **Low** | Screen_Manager.py:133–135 | Console tag colors: warning `#ffcc00` (yellow) and success `#34eb49` (light green) on a white background are barely legible. | Use darker tones (e.g. `#b58900`, `#1e8e3e`). |
| **Low** | Screen_Manager.py:62–63, 119–129 | Window is resizable but content uses fixed character widths and `sticky` anchors; enlarging the window grows dead space, shrinking clips widgets. No minimum size set. | Set `minsize()`, give listboxes/consoles `weight=1` expansion, or disable horizontal resize. |
| **Low** | Screen_Manager.py:284–300 | Multi-select listboxes with no Select All / Clear; no keyboard shortcuts; no confirmation before "Delete Playlist(s)" on the Plex server. | Add a delete confirmation dialog and Select All/None buttons. |

## 3. Robustness / Error Handling
| Severity | File:Line | Issue | Recommendation |
|---|---|---|---|
| **Critical** | API_Calls.py:35; Music_Database_Import.py:79 | `exit('Plex Server Not Responding')` / `exit(500)` inside library code terminates the entire GUI app with no chance to recover or read the message. | Raise a custom exception; catch at the UI layer and post to the status console. |
| **Critical** | Music_Database_Import.py:82,101,104 vs Plex_Playlist_Import_Main.py:221–222 | `find_playlist_keys()` returns `False` on file errors, but the caller immediately does `len(playlist_keys)` → `TypeError: object of type 'bool' has no len()` → unhandled crash in a Tk callback. | Return `[]` on failure, or check `if not playlist_keys` before `len()`. |
| **High** | API_Calls.py:39–46, 96–117, 147–199, 239–252 | Most API functions have zero error handling: no timeouts, no `raise_for_status()`, `response.json()` on possibly non-JSON bodies, `data["MediaContainer"]["Metadata"]` KeyError when empty. Any server hiccup raises an uncaught exception inside a Tkinter callback — invisible in a windowed .exe. | Central request helper: `requests.Session` with `timeout=`, retries (urllib3 `Retry`), `raise_for_status()`, and one exception type surfaced to the status console. Install a `tk.Tk.report_callback_exception` handler as a safety net. |
| **High** | Plex_Playlist_Import_Main.py:105–106, 81 | `@lru_cache` on `get_plex_information(app, count_photos)` caches server info forever. After reconnecting to a *different* server (or rebuilding libraries), imports silently use the old machine ID and library keys. Same issue for `get_photo_library_count`. | Remove `lru_cache`; cache in an attribute and invalidate on every successful login. (Also: caching on the unhashable-by-content `app` object is fragile.) |
| **High** | Music_Database_Import.py:16–19, 27–60 | If the DB build is interrupted (crash, network loss mid-loop), a *partial* file remains and the `os.path.isfile` check treats it as complete forever after. File is opened without a context manager, so it also stays open on exception. | Write to a temp file and `os.replace()` on success; use `with open(...)`. |
| **High** | Music_Database_Import.py:75, 97 | m3u and DB files are opened strictly as UTF-8. iTunes for Windows exports `.m3u` in ANSI (cp1252) — any accented artist/title raises `UnicodeDecodeError`, which (via the False-return bug above) crashes the import. | Open m3u with `encoding="utf-8-sig", errors="replace"` after trying cp1252 fallback, or detect via `charset-normalizer`. Support `.m3u8` too. |
| **Medium** | Music_Database_Import.py:31–34, 48–52 | DB build assumes every track has `Media[0].Part[0].file` and a 3-deep artist/album/title path. Tracks at library root or with missing media → IndexError; `song_count == 0` → ZeroDivisionError at line 57. | Wrap per-track parsing in try/except, skip+log malformed tracks, guard the percent calculation. |
| **Medium** | Plex_Playlist_Import_Main.py:235–238 | An existing Plex playlist with the same name is deleted without confirmation — destructive if the user curated it on the server side. | Ask (messagebox) before replacing, or rename the new one. |
| **Medium** | Music_Database_Import.py:91 | `int(music_list[0])` and indexing `music_list[1..3]` on a possibly corrupted/truncated DB line → ValueError/IndexError, uncaught. | Validate line shape; skip and warn on malformed lines. |
| **Medium** | Plex_Login.py:125 | `float(app.ip_timer.get())/1000` — empty or non-numeric timeout field (validation is broken, see §2) raises uncaught ValueError mid-login. | Parse once up front with try/except and a sane default (1000 ms). |
| **Low** | API_Calls.py:144 | `search_for_song` returns the raw `Response` object when no match is found, while matches return a string key — inconsistent type for callers. | Return `None` on no match. |
| **Low** | Plex_Playlist_Import_Main.py:64–79 | Recursive photo-directory walk has no depth limit (commented-out runaway guard suggests it has looped before) and uses module-level `global photo_count`. | Iterative walk with an explicit stack; pass count as return value. |

## 4. Performance / Speed
| Severity | File:Line | Issue | Recommendation |
|---|---|---|---|
| **High** | Screen_Manager.py (all callbacks); Plex_Login.py:118–135; Music_Database_Import.py:42–58 | Every long operation — IP scan (up to N × timeout seconds), DB build (one HTTP call per 100 tracks of the whole library), playlist import — runs on the Tk main thread. The UI freezes except when `top.update()` is called, which conversely allows re-entrancy (user can click Import again mid-import). | Run long work in `threading.Thread`, marshal UI updates back via `app.after()` / a queue, and disable the triggering buttons while running. |
| **Medium** | Music_Database_Import.py:129–141 | Playlist matching is O(tracks × playlist) with three string compares per pair — a 50k-track library × 500-song playlist = 25M iterations in pure Python. | Build a dict keyed on `(artist, album, track)` once → O(1) lookups. |
| **Medium** | Plex_Playlist_Import_Main.py:199 vs Screen_Manager.py:347 | `get_plex_information()` re-walks every library section (one metadata request each) on each call; only `lru_cache` (itself a correctness bug, §3) hides this. Login also triggers `update_info_screen` + `display_plex_playlists` serially. | After removing `lru_cache`, fetch sections once per login and reuse; only the Music section is needed for imports. |
| **Low** | API_Calls.py:120–128 | `add_song_to_playlist` (single-song variant) re-downloads the whole playlist after every add. It appears unused — the batched `add_songs_to_Plex_playlist` (50/request) is good. | Delete the unused function or drop the trailing fetch. |
| **Low** | Music_Database_Import.py:40 | Page size of 100 tracks/request means 500 round-trips for a 50k library. | Raise `X-Plex-Container-Size` to 1000+ (Plex handles it fine). |

## 5. Windows Application Best Practices
| Severity | File:Line | Issue | Recommendation |
|---|---|---|---|
| **High** | (everywhere — e.g. Plex_Login.py:15,39; Music_Database_Import.py:17; API_Calls.py:28) | ~50 `print()` calls as the only diagnostics. In a PyInstaller windowed .exe stdout is discarded, so field debugging is impossible — and several prints leak secrets (§1). | Replace with `logging`: console handler in dev, rotating file handler at `%LOCALAPPDATA%\iTunesToPlex\logs\`, token-redacting formatter. |
| **Medium** | Music_Database_Import.py:13–14; Plex_Playlist_Import_Main.py:217 | App data (`Plex Music Database.txt`) is written into the user's m3u/music folder — polluting user content and breaking if that folder is read-only (e.g. on a NAS share). | Store under `%LOCALAPPDATA%\iTunesToPlex\` (`os.getenv("LOCALAPPDATA")`). |
| **Medium** | Screen_Manager.py:17–60 | No window/app icon, no version string in the title, and (per repo) no .exe version resource — Windows shows the generic Tk feather and SmartScreen flags unsigned, unversioned binaries more aggressively. | Add `iconbitmap()`, embed version info via PyInstaller `--version-file`, and consider code signing. |
| **Low** | Screen_Manager.py / main.py | No `WM_DELETE_WINDOW` handler. Harmless today (no threads, file handles closed promptly except the §3 case), but will bite once work moves off the main thread. | Add a `protocol("WM_DELETE_WINDOW", ...)` handler that signals worker threads to stop. |
| **Low** | Screen_Manager.py:444–456; README.md:11 | Good: m3u folder uses `Path.home()` + a file dialog rather than hardcoded paths. README's `c:\Users\USERNAME\...` is instructional only. | Also handle OneDrive-redirected `Music` folders (`Path.home()/OneDrive/Music`). |
| **Low** | Screen_Manager.py:139,168 | Hardcoded `('Arial', 10)` fonts ignore Windows display scaling preferences. | Use the named font `TkDefaultFont` and relative size adjustments. |

## 6. Code Quality / Maintainability
| Severity | File:Line | Issue | Recommendation |
|---|---|---|---|
| **Medium** | globals.py | Mutable module-level globals for connection state, written from three modules. Untestable, and the stale-cache bug (§3) is a direct consequence. | Introduce a `PlexConnection` dataclass (ip, port, token, session) passed explicitly; one place to reset on re-login. |
| **Medium** | (repo) | No tests of any kind. The pure logic — m3u parsing, DB line parsing, key matching, URL building — is easily testable without a server. | Start with pytest units for `find_playlist_keys` (ANSI/UTF-8 fixtures, malformed lines, `\` vs `/` paths) and a `responses`-mocked test for `add_songs_to_Plex_playlist` batching. |
| **Low** | Music_Database_Import.py:11 (`libray_name`), API_Calls.py:48 (`Libray`), naming mix of snake/Pascal files | Typos and inconsistent naming; "database" misnames a flat text file. | Rename during the refactor; consider SQLite for real (indexed lookups would also fix §4 matching). |
| **Low** | API_Calls.py, Plex_Login.py (throughout) | Large amounts of commented-out debug code and dead functions (`check_song_in_playlist`, `add_song_to_playlist`, `get_plex_attribute`). | Delete; git history preserves them. |
| **Low** | Screen_Manager.py:119,333 | `create_common_console` overwrites `self.status_console` three times; only the list saves it. Posting every message to all three consoles works but duplicates state. | Use one console instance per page keyed by tab, post to the active tab. |

---

## Top 5 Actions for the Next Pass
1. **Stop leaking credentials** — remove the password/token `print()`s (Plex_Login.py:45,56,122,138,151; API_Calls.py:28), mask the password field (`show="*"`), drop the token row from the info tab, and move the token out of URL query strings.
2. **Eliminate hard exits and the `len(False)` crash** — replace `exit()` in API_Calls.py:35 and Music_Database_Import.py:79 with exceptions surfaced to the status console; make `find_playlist_keys` return `[]` on failure.
3. **Add a central, error-handled HTTP layer** — one `requests.Session` wrapper with timeouts, retries, `raise_for_status()`, and URL-encoding of all dynamic parameters; remove the `lru_cache` stale-state bug and reset state on re-login.
4. **Move long operations off the UI thread** — IP scan, DB build, and import in worker threads with `after()`-based progress updates and disabled buttons; fixes both freezes and re-entrancy.
5. **Fix the music-database lifecycle** — atomic temp-file build, cp1252/UTF-8 m3u handling, storage in `%LOCALAPPDATA%`, and a visible "Rebuild Database" button with staleness detection.
