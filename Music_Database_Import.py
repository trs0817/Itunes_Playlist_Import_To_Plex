# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ultimation LLC and Robert C Suffern
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import API_Calls
import os


def save_music_database(app, libray_name, library_id, song_count, output_file_path):

    file_name = "Plex Music Database.txt"
    database_name = output_file_path / file_name

    if os.path.isfile(str(database_name)):               # Don't create a new database file if one already exists
        print(str(database_name) + " already exists, not refreshed.")
        app.post_to_status_console(f"Plex music database {file_name} already exists, not refreshed.", "info")
        return database_name
    else:
        result = app.music_database_create_MB()
        if not result:
            return False

        app.post_to_status_console(f"Creating music database {file_name}", "info")
        app.create_progressbar("Creating the Music Database", "determinate")
        output_playlist = open(database_name, 'wt', encoding='utf-8')

    # ------- To save space remove everything in the path except artist, album, title.  To do that, find the position of the last byte of the redundant data

        track_info = API_Calls.get_track_data(library_id, 0, 1)  # Get the first track to record the path to the music
        track_info = track_info[0]
        path = track_info['Media'][0]['Part'][0]['file']
        position = path.find(libray_name + "/") + len(libray_name) + 1
        common_path = path[0:position]
        output_playlist.write("The Plex path for Music is: " + common_path + "\n")      # ---- Output to the first line of the database file

    # ----------  Loop through the entire library saving the ratingKey, and the song file path less the common element to all paths
        track_count_start = 0
        number_of_tracks_to_get = 100
        index = number_of_tracks_to_get
        while index == number_of_tracks_to_get:
            print(track_count_start)
            index = 0
            track_info = API_Calls.get_track_data(library_id, track_count_start, number_of_tracks_to_get)       # Returns the list of tracks in JSON format
            for track in track_info:
                key = track['ratingKey']
                path = track['Media'][0]['Part'][0]['file']
                path = path[position:]          # get rid of the redundant path info to save file space
                track_data = path.split("/")

                output_string = "{}:::{}:::{}:::{}\n".format(key, track_data[0].lower(), track_data[1].lower(), track_data[2].lower())    # Using ::: as a delimiter to avoid any issues with a colon being in the information                                                                                                                                          # Plex does some wierd things with capitalization so moving everything to lower case to make the match easie
                output_playlist.write(output_string)
                index = index + 1
            track_count_start = track_count_start + number_of_tracks_to_get
            percent_done = (track_count_start / song_count) * 100
            app.update_progressbar(percent_done)

        output_playlist.close()
        app.post_to_status_console(f"Plex music database {file_name} created.", "success")
        app.close_progressbar()

        #track_info = track_info.json()
        #print(json.dumps(track_info, indent=4))
        return database_name


#-------------------  Create a list of database track keys from the list of songs in the playlist
def find_playlist_keys(app, m3u_playlist, music_database, working_directory):

    # Move the Plex music database into RAM for speed and create a list of dictionaries that contain the track info
    music_database = working_directory / music_database
    try:
        with open(str(music_database), 'r', encoding='utf-8') as file:
            file_content = file.read().splitlines()
    except FileNotFoundError:
        print(f"Error: The file '{music_database}' was not found.")
        exit(500)
    except Exception as e:
        print(f"An error occurred: {e}")
        return False

    file_content.pop(0)         # skip first line

    music_database = []
    music_item = {}

    for music_line in file_content:
        music_list = music_line.split(":::")
        music_item = {'Key': int(music_list[0]), 'Artist': music_list[1], 'Album': music_list[2], "Track": music_list[3]}
        music_database.append(music_item)

    # Move the new playlist info into RAM for speed and create a list of dictionaries that contain the track info
    m3u_playlist = working_directory / m3u_playlist
    try:
        with open(str(m3u_playlist), 'rt', encoding='utf-8') as file:
            file_content = file.read().splitlines()
    except FileNotFoundError:
        print(f"Error: The file '{m3u_playlist}' was not found.")
        exit(501)
        return False
    except Exception as e:
        print(f"An error occurred: {e}")
        return False

    playlist_database = []
    playlist_item = {}

    for music_line in file_content:
        if music_line == "#EXTM3U":
            continue
        if music_line[0:7] == "#EXTINF":
            continue
        music_item = music_line.split("\\")
        length = len(music_item)
        if length < 3:
            music_item = music_line.split("/")
            length = len(music_item)
        #print(length)
        if length < 3:
            continue

        playlist_item = {'Artist': music_item[length-3].lower(), 'Album': music_item[length-2].lower(), 'Track': music_item[length-1].lower()}      # Plex does some wierd things with capitalization so moving everything to lower case to make the match easier
        playlist_database.append(playlist_item)

    # Now match the playlist item to the music database item and return a list of keys
    key_list = []
    found = False
    for playlist_track in playlist_database:

        for track in music_database:
            if track['Track'] == playlist_track['Track']:
                if track['Album'] == playlist_track['Album']:
                    if track['Artist'] == playlist_track['Artist']:         # if all three attributes are an exact match then the song has been found
                        key_list.append(track['Key'])
                        #print('Track Found')
                        found = True
        if found == False:
            print(f"Track = {playlist_track['Track']} Album = {playlist_track['Album']} Artist = {playlist_track['Artist']} was not found.")
            app.post_to_status_console(f"Track = {playlist_track['Track']} Album = {playlist_track['Album']} Artist = {playlist_track['Artist']} was not found on Plex server.", "error")
        found = False
    app.post_to_status_console(f"Of the {len(playlist_database)} songs in playlist {m3u_playlist}, {len(key_list)} were found on the Plex server.", "info")
    return key_list
