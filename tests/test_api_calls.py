"""Tests for API_Calls._request() and add_songs_to_Plex_playlist()

Covers:
- _request() raises PlexAPIError on a non-2xx HTTP response
- _request() raises PlexAPIError on a connection error (not raw requests exception)
- add_songs_to_Plex_playlist() batches in groups of 50
- add_songs_to_Plex_playlist() returns (song_count, return_size) correctly
"""
import sys
import pathlib
import json
from unittest.mock import patch, MagicMock

import pytest
import responses as responses_lib

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# Patch globals before importing API_Calls so module-level Session is created
import globals
globals.PLEX_IP_ADDRESS = "192.168.1.1"
globals.PLEX_PORT = "32400"
globals.PLEX_TOKEN = "test_token"

import API_Calls
from API_Calls import PlexAPIError, _request

BASE = "http://192.168.1.1:32400"


# ---------------------------------------------------------------------------
# _request — non-2xx raises PlexAPIError
# ---------------------------------------------------------------------------

@responses_lib.activate
def test_request_http_error_raises_plex_api_error():
    responses_lib.add(responses_lib.GET, f"{BASE}/test", status=404)
    with pytest.raises(PlexAPIError, match="404"):
        _request("GET", f"{BASE}/test",
                 headers={"X-Plex-Token": "t"}, timeout=5)


@responses_lib.activate
def test_request_server_error_raises_plex_api_error():
    responses_lib.add(responses_lib.GET, f"{BASE}/test", status=500)
    with pytest.raises(PlexAPIError):
        _request("GET", f"{BASE}/test",
                 headers={"X-Plex-Token": "t"}, timeout=5)


# ---------------------------------------------------------------------------
# _request — connection error raises PlexAPIError (not raw requests exception)
# ---------------------------------------------------------------------------

@responses_lib.activate
def test_request_connection_error_raises_plex_api_error():
    import requests
    responses_lib.add(
        responses_lib.GET, f"{BASE}/test",
        body=requests.exceptions.ConnectionError("connection refused")
    )
    with pytest.raises(PlexAPIError):
        _request("GET", f"{BASE}/test",
                 headers={"X-Plex-Token": "t"}, timeout=5)


@responses_lib.activate
def test_request_timeout_raises_plex_api_error():
    import requests
    responses_lib.add(
        responses_lib.GET, f"{BASE}/test",
        body=requests.exceptions.Timeout("timed out")
    )
    with pytest.raises(PlexAPIError):
        _request("GET", f"{BASE}/test",
                 headers={"X-Plex-Token": "t"}, timeout=1)


# ---------------------------------------------------------------------------
# _request — 2xx succeeds and returns the response
# ---------------------------------------------------------------------------

@responses_lib.activate
def test_request_success_returns_response():
    responses_lib.add(responses_lib.GET, f"{BASE}/test", status=200,
                      json={"ok": True})
    resp = _request("GET", f"{BASE}/test",
                    headers={"X-Plex-Token": "t"}, timeout=5)
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


# ---------------------------------------------------------------------------
# add_songs_to_Plex_playlist — batching and return values
# ---------------------------------------------------------------------------

def _make_put_response(size):
    """Return value for get_playlist_contents: MediaContainer with `size` items."""
    return {
        "MediaContainer": {
            "size": size,
            "Metadata": [{"ratingKey": str(i)} for i in range(size)]
        }
    }


@responses_lib.activate
def test_add_songs_batches_50():
    """120 songs should produce 3 PUT requests (50 + 50 + 20)."""
    machine_id  = "abc123"
    playlist_id = "999"
    song_list   = list(range(1, 121))   # 120 songs

    put_url = f"{BASE}/playlists/{playlist_id}/items"
    contents_url = f"{BASE}/playlists/{playlist_id}/items"

    # Register PUT for all batches (responses matches by URL prefix)
    for _ in range(3):
        responses_lib.add(responses_lib.PUT, put_url, status=200,
                          json={"MediaContainer": {}})

    # Final GET for get_playlist_contents
    responses_lib.add(responses_lib.GET, contents_url, status=200,
                      json=_make_put_response(120))

    song_count, return_size = API_Calls.add_songs_to_Plex_playlist(
        machine_id, playlist_id, song_list)

    assert song_count == 120
    assert return_size == 120

    put_calls = [c for c in responses_lib.calls if c.request.method == "PUT"]
    assert len(put_calls) == 3


@responses_lib.activate
def test_add_songs_exact_batch_boundary():
    """50 songs exactly should produce 1 PUT (the last-batch path)."""
    machine_id  = "abc123"
    playlist_id = "888"
    song_list   = list(range(1, 51))

    put_url      = f"{BASE}/playlists/{playlist_id}/items"
    contents_url = f"{BASE}/playlists/{playlist_id}/items"

    responses_lib.add(responses_lib.PUT, put_url, status=200,
                      json={"MediaContainer": {}})
    responses_lib.add(responses_lib.GET, contents_url, status=200,
                      json=_make_put_response(50))

    song_count, return_size = API_Calls.add_songs_to_Plex_playlist(
        machine_id, playlist_id, song_list)

    assert song_count == 50
    assert return_size == 50
    put_calls = [c for c in responses_lib.calls if c.request.method == "PUT"]
    assert len(put_calls) == 1
