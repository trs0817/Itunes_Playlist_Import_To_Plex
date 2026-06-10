# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ultimation LLC and Robert C Suffern
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import requests
import urllib.parse
import xmltodict
from plexapi.server import PlexServer
import globals
import logging
logger = logging.getLogger(__name__)


class PlexConnectionError(Exception):
    """Raised when a Plex server connection fails unrecoverably."""


class PlexAPIError(PlexConnectionError):
    """Raised when a Plex API HTTP call fails."""


# Module-level session and default timeout shared by all API calls.
_SESSION = requests.Session()
_DEFAULT_TIMEOUT = 10  # seconds


def _request(method, url, **kwargs):
    """Central HTTP helper: adds a default timeout, calls raise_for_status(),
    and converts any requests exception into PlexAPIError."""
    kwargs.setdefault('timeout', _DEFAULT_TIMEOUT)
    try:
        response = _SESSION.request(method, url, **kwargs)
        response.raise_for_status()
        return response
    except requests.exceptions.HTTPError as e:
        raise PlexAPIError(
            f"Plex API error {e.response.status_code} ({e.response.reason}) for {url}"
        ) from e
    except requests.exceptions.RequestException as e:
        raise PlexAPIError(f"Plex request failed: {e}") from e


def get_globals():
    baseurl = f'http://{globals.PLEX_IP_ADDRESS}:{globals.PLEX_PORT}'
    token = globals.PLEX_TOKEN
    headers = {
        'X-Plex-Token': globals.PLEX_TOKEN,
        'Accept': 'application/json'
    }
    return baseurl, token, headers


def connect_plex():
    baseurl, token, headers = get_globals()
    try:
        plex = PlexServer(baseurl, token)
        logger.info("Plex server is responding")
        return plex
    except Exception as e:
        raise PlexConnectionError(f'Plex Server Not Responding: {e}') from e


#-------- Get a particular attribute of the Plex Server
def get_plex_attribute(identifier):
    baseurl, token, headers = get_globals()
    response = _request('GET', baseurl, headers=headers)
    data = response.json()
    attribute = data['MediaContainer'][identifier]
    return attribute


#---------- Get and return a list of the Library Sections
def get_library_sections():
    baseurl, token, headers = get_globals()
    url = baseurl + "/library/sections/"
    response = _request('GET', url, headers=headers)
    return response.json()


#------- Get List of Playlists
def get_playlists():
    baseurl, token, headers = get_globals()
    url = baseurl + "/playlists?playlistType=audio"
    try:
        response = _request('GET', url, headers=headers)
        data = response.json()
        if data["MediaContainer"]["size"] == 0:
            return []
        return data["MediaContainer"]["Metadata"]
    except PlexAPIError as e:
        logger.error("Plex API error fetching playlists: %s", e)
        return []


#-------- Get Specific Playlist
def get_playlist_metadata(identifier):
    baseurl, token, headers = get_globals()
    url = baseurl + "/playlists/" + identifier + "?checkfiles=1"
    response = _request('GET', url, headers=headers)
    return response.json()


#-------- Get List of Songs in the Playlist
def get_playlist_contents(identifier):
    baseurl, token, headers = get_globals()
    url = baseurl + '/playlists/' + identifier + '/items?checkfiles=1'
    response = _request('GET', url, headers=headers)
    return response.json()


#-------- Add a song to a playlist
def add_song_to_playlist(machine_ID, playlist, song):
    baseurl, token, headers = get_globals()
    url = (baseurl + "/playlists/" + playlist + "/items?uri=server://" +
           machine_ID + "/com.plexapp.plugins.library/library/metadata/" + song)
    _request('PUT', url, headers=headers)
    return get_playlist_contents(playlist)


#----------  Search for a particular song in the library — returns ratingKey or None
def search_for_song(library, artist, album, song):
    baseurl, token, headers = get_globals()
    url = baseurl + "/library/sections/" + library + "/search"
    response = _request('GET', url, headers=headers,
                        params={'type': 10, 'query': song})
    data = response.json()
    metadata = data.get("MediaContainer", {}).get("Metadata") or []
    for item in metadata:
        if item.get("parentTitle") == album and item.get("grandparentTitle") == artist:
            return item["ratingKey"]
    return None


#-------------- Get the metadata for a particular library (returns XML via xmltodict)
def get_library_metadata(library_id):
    baseurl, token, headers = get_globals()
    xml_headers = {'X-Plex-Token': globals.PLEX_TOKEN, 'Accept': 'application/xml'}
    url = baseurl + "/library/sections/" + library_id + "/all"
    response = _request('GET', url, headers=xml_headers)
    return xmltodict.parse(response.text)


#-------------  Get music track metadata with a start track index and number of tracks
def get_metadata(library, content_type, start, number):
    baseurl, token, headers = get_globals()
    url = (baseurl + "/library/sections/" + library +
           "/all?type=" + str(content_type) +
           "&X-Plex-Container-Start=" + str(start) +
           "&X-Plex-Container-Size=" + str(number))
    response = _request('GET', url, headers=headers)
    return response.json()


#-------------  Get music track metadata with a start track index and number of tracks
def get_track_data(library, start, number):
    baseurl, token, headers = get_globals()
    url = (baseurl + "/library/sections/" + library +
           "/all?type=10&X-Plex-Container-Start=" + str(start) +
           "&X-Plex-Container-Size=" + str(number))
    response = _request('GET', url, headers=headers)
    data = response.json()
    return data["MediaContainer"]["Metadata"]


#-------------  Delete a playlist whose ratingKey = key
def delete_playlist(key):
    baseurl, token, headers = get_globals()
    url = baseurl + "/playlists/" + key
    _request('DELETE', url, headers=headers)
    return True


#-------------  Create a playlist (name is URL-encoded to handle & # etc.)
def create_playlist(machine_id, name, library_id):
    baseurl, token, headers = get_globals()
    encoded_name = urllib.parse.quote(name, safe='')
    url = (baseurl + "/playlists?type=audio&title=" + encoded_name +
           "&smart=0&uri=server://" + machine_id +
           "/com.plexapp.plugins.library/" + library_id)
    response = _request('POST', url, headers=headers)
    return response.json()


#----------------- Add a list of songs to a playlist
def add_songs_to_Plex_playlist(machine_ID, playlist_id, song_list):
    baseurl, token, headers = get_globals()
    song_count = len(song_list)
    logger.info("Importing %d songs to playlist", song_count)
    number_of_tracks_to_add = 50
    list_count = 0
    songs = ""
    for track_count in range(song_count):
        list_count += 1
        songs = songs + str(song_list[track_count])
        if list_count == number_of_tracks_to_add:
            url = (baseurl + "/playlists/" + playlist_id +
                   "/items?uri=server://" + machine_ID +
                   "/com.plexapp.plugins.library/library/metadata/" + songs)
            _request('PUT', url, headers=headers)
            list_count = 0
            logger.debug("Batch progress: %d tracks sent", track_count + 1)
            songs = ""
            continue
        songs = songs + ","
    # Send the last batch
    if list_count > 0:
        url = (baseurl + "/playlists/" + playlist_id +
               "/items?uri=server://" + machine_ID +
               "/com.plexapp.plugins.library/library/metadata/" + songs[:-1])
        _request('PUT', url, headers=headers)
        logger.debug("Batch progress: %d tracks sent", track_count + 1)

    data = get_playlist_contents(playlist_id)
    return_size = data['MediaContainer']['size']
    if return_size == song_count:
        logger.info("Successfully added songs to playlist")
    else:
        logger.warning("Failed to add all songs to playlist")

    return song_count, return_size


#--------------  Get the metadata of an item (XML via xmltodict)
def get_item_metadata(identifier):
    baseurl, token, headers = get_globals()
    xml_headers = {'X-Plex-Token': globals.PLEX_TOKEN, 'Accept': 'application/xml'}
    url = baseurl + "/library/metadata/" + str(identifier) + "/children/"
    response = _request('GET', url, headers=xml_headers)
    return xmltodict.parse(response.text)
