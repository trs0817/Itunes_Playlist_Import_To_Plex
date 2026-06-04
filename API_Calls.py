# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ultimation LLC and Robert C Suffern
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import requests
import xmltodict
from plexapi.server import PlexServer
import globals

def get_globals():
    baseurl = f'http://{globals.PLEX_IP_ADDRESS}:{globals.PLEX_PORT}'
    token = globals.PLEX_TOKEN
    headers = {
        'X-Plex-Token': globals.PLEX_TOKEN,
        'Accept': 'application/json'  # This header tells Plex to return JSON
    }
    return baseurl, token, headers


def connect_plex():

    # Assuming 'baseurl' is your Plex Media Server URL
    # and 'token' is your authentication token

    baseurl, token, headers = get_globals()
    print(f"Connecting to Plex Server: {baseurl} with token: {token}...")
    try:
        plex = PlexServer(baseurl, token)  # Corrected argument name
        print("Plex server is responding")
        return plex
    except TypeError as e:
        print(f"Error connecting to Plex: {e}")
        exit('Plex Server Not Responding')


#-------- Get a particular attribute of the Plex Server
def get_plex_attribute(identifier):
    baseurl, token, headers = get_globals()
    response = requests.get(baseurl, headers=headers)
    data = response.json()
    #print(json.dumps(data, indent=4))
    #print(data)
    attribute=data['MediaContainer'][identifier]
    return attribute

#---------- Get and return a list of the Libray Sections
def get_library_sections():
    baseurl, token, headers = get_globals()
    api_info = "/library/sections/"
    url = baseurl + api_info
    response = requests.get(url, headers=headers)

    # Pretty-print the JSON data
    data = response.json()
    #print(json.dumps(data, indent=4))

    return data


#------- Get List of Playlists
def get_playlists():
    baseurl, token, headers = get_globals()
    api_info ="/playlists?playlistType=audio"
    url = baseurl + api_info
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()                         # If there was an HTTP error, this will raise the HTTP exceptions that follow
        # Pretty-print the JSON data
        data = response.json()
        #print(json.dumps(data, indent=4))
        if data["MediaContainer"]["size"] == 0:             # Check to make sure there are playlists in the library
            return []
        data = data["MediaContainer"]["Metadata"]
        return data
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            print("Plex API Error - Unauthorized")
        elif e.response.status_code == 403:
            print("Plex API Error -Forbidden")
        elif e.response.status_code == 404:
            print("Plex API Error -Not found")
        else:
            print(f"Plex API Error - HTTP error: {e.response.status_code}")

    except requests.exceptions.RequestException as e:       # This except will trigger if the request fails for any other reason (bad URL)
        print(f"Plex API Error - URL Request Invalid or Failed: {e}")

    return []



#-------- Get Specific Playlist

def get_playlist_metadata(identifier):
    baseurl, token, headers = get_globals()
    api_info = "/playlists/" + identifier + "?checkfiles=1"
    url = baseurl + api_info
    response = requests.get(url, headers=headers)

    # Pretty-print the JSON data
    data = response.json()
    #print(json.dumps(data, indent=4))
    return data

#-------- Get List of Songs in the Playlist
def get_playlist_contents(identifier):
    baseurl, token, headers = get_globals()
    api_info = '/playlists/' + identifier + '/items?checkfiles=1'
    url = baseurl + api_info
    response = requests.get(url, headers=headers)

    # Pretty-print the JSON data
    data = response.json()
    #print(json.dumps(data, indent=4))
    return data

#-------- Add a song to a playlist (use the Track "ratingKey" from the XML of the song you want to add as the track identifier)
def add_song_to_playlist(machine_ID, playlist, song):
    baseurl, token, headers = get_globals()
    api_info = "/playlists/" + playlist + "/items?uri=server://" + machine_ID + "/com.plexapp.plugins.library/library/metadata/" + song
    url = baseurl + api_info
    response = requests.put(url, headers=headers)           # returns playlist metadata
    data = get_playlist_contents(playlist)                  # returns playlist content in JSON format
    # Pretty-print the JSON data
    #print(json.dumps(data, indent=4))
    return data

#----------  Search for a particular song in the library and return the ratingKey
def search_for_song(library, artist, album, song):
    baseurl, token, headers = get_globals()
    api_info = "/library/sections/" + library + "/search?type=10&query=" + song
    url = baseurl + api_info
    response = requests.get(url, headers=headers)  # returns playlist metadata

    # Pretty-print the JSON data
    data = response.json()
    #print(json.dumps(data, indent=4))
    data = data["MediaContainer"]["Metadata"]
    for item in data:
        if item["parentTitle"] == album and item["grandparentTitle"] == artist :
            return item["ratingKey"]
    return response

#-------------- Get the metadata for a particular library
def get_library_metadata(library_id):
    baseurl, token, headers = get_globals()
    headers2 = {
        'X-Plex-Token': token,
        'Accept': 'application/xml'  # This header tells Plex to return XML
    }
    api_info = "/library/sections/" + library_id + "/all"
    url = baseurl + api_info
    response = requests.get(url, headers=headers2)           # returns section metadata
    data = xmltodict.parse(response.text)                   # returning XML provides a number of XML tags that response.json leaves out
    # Pretty-print the JSON data
    #data = response.json()
    #rint(json.dumps(data, indent=4))
    return data

#-------------  Get music track metadata with a start track index and number of tracks
def get_metadata(library, content_type, start, number):
    baseurl, token, headers = get_globals()
    api_info = "/library/sections/" + library + "/all?type=" + str(content_type) + "&X-Plex-Container-Start=" + str(start) + "&X-Plex-Container-Size=" + str(number)
    url = baseurl + api_info
    response = requests.get(url, headers=headers)
    data = response.json()
    #print(json.dumps(data, indent=4))
    return data

#-------------  Get music track metadata with a start track index and number of tracks
def get_track_data(library, start, number):
    baseurl, token, headers = get_globals()
    api_info = "/library/sections/" + library + "/all?type=10&X-Plex-Container-Start=" + str(start) + "&X-Plex-Container-Size=" + str(number)
    url = baseurl + api_info
    response = requests.get(url, headers=headers)
    data = response.json()
    data = data["MediaContainer"]["Metadata"]
    #print(json.dumps(data, indent=4))
    return data

#-------------  Delete a playlist whose ratingKey = key
def delete_playlist(key):
    baseurl, token, headers = get_globals()
    api_info ="/playlists/" + key
    url = baseurl + api_info
    response = requests.delete(url, headers=headers)
    return True

#-------------  Create a playlist
def create_playlist(machine_id, name, library_id):
    baseurl, token, headers = get_globals()
    api_info = "/playlists?type=audio&title=" + name + "&smart=0&uri=server://" + machine_id + "/com.plexapp.plugins.library/" + library_id
    url = baseurl + api_info
    response = requests.post(url, headers=headers)
    data = response.json()
    #print(json.dumps(data, indent=4))
    return data

#----------------- Add a list of songs to a playlist
def add_songs_to_Plex_playlist(machine_ID, playlist_id, song_list):
    baseurl, token, headers = get_globals()
    song_count = len(song_list)
    print('Number of songs to import:', str(song_count))
    number_of_tracks_to_add = 50
    track_count = 0
    list_count = 0
    songs = ""
    for track_count in range(song_count):
        list_count += 1
        songs = songs + str((song_list[track_count]))
        if list_count == number_of_tracks_to_add:
            api_info = "/playlists/" + playlist_id + "/items?uri=server://" + machine_ID + "/com.plexapp.plugins.library/library/metadata/" + songs
            url = baseurl + api_info
            response = requests.put(url, headers=headers)  # returns playlist metadata
            list_count = 0
            print(track_count+1)
            songs = ""
            continue
        songs = songs + ","
    # send the last remaining songs in the list
    if list_count > 0:
        api_info = "/playlists/" + playlist_id + "/items?uri=server://" + machine_ID + "/com.plexapp.plugins.library/library/metadata/" + songs[:-1]
        url = baseurl + api_info
        response = requests.put(url, headers=headers)  # returns playlist metadata
        print(track_count+1)

    data = get_playlist_contents(playlist_id)                     # returns playlist content in JSON format
    return_size = data['MediaContainer']['size']
    if return_size == song_count:
        print("Successfully added songs to playlist!")
    else:
        print("Failed to add songs to playlist!")

    return song_count, return_size

#--------------  Get the metadata of an item
def get_item_metadata(identifier):
    # The requests JSON parser eliminates some relevant XML tags, so I am requesting the XML and then using xmltodict to parse it
    baseurl, token, headers = get_globals()
    headers2 = {
        'X-Plex-Token': token,
        'Accept': 'application/xml'  # This header tells Plex to return XML
    }
    api_info = "/library/metadata/" + str(identifier) + "/children/"        # adding children returns the metadata for all the items that may be in the identifier
    url = baseurl + api_info
    response = requests.get(url, headers=headers2)
    #print(response.text)                        # print out the XML data
    data = xmltodict.parse(response.text)       # parse using xmltodict
    #print(json.dumps(data, indent=4))
    return data