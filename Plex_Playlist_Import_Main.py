# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ultimation LLC and Robert C Suffern
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import API_Calls
import Music_Database_Import
from functools import lru_cache
import globals

#-----------------------  LOCAL FUNCTIONS
# pass JSON dictionary of playlist and search for a song ID
def check_song_in_playlist(content, song):
    content = content["MediaContainer"]["Metadata"]
    for song_info in content:
        if song_info['ratingKey'] == song:
            return True
    return False

def get_content_type(content):
    #  Note: The content type number for the show description is changed to episodes to get the total count of show episodes rather than the total count of shows,
    #  the content type for artist is changed to track to get the total number of tracks and not the total number of artists
    type_map = {
    'movie':	        1,
    'show': 	        4,          # Plex code is 2
    'season':	        3,
    'episode':	        4,
    'trailer':	        5,
    'person':	        7,
    'artist':	        10,         # Plex code is 8
    'album':	        9,
    'track':	        10,
    'clip': 	        12,
    'photo':	        13,
    'photoalbum':       14,
    'playlist':         15,
    'playlistfolder':   16,
    'collection':   	18
    }
    return type_map.get(content)

def count_photos_in_metadata(metadata):
    count = 0
    photo_metadata = metadata.get('Photo', [])  # Return empty list if no photos
    if isinstance(photo_metadata, dict):  # If only one photo, it comes back as a dictionary, not a list
        photo_metadata = [photo_metadata]  # Convert to a list
    for item in photo_metadata:
        #print(json.dumps(item, indent=4))
        count += 1
        #print(count)
    return count

def get_directories_in_metadata(metadata):
    directories = []
    directory_metadata = metadata.get('Directory', [])
    if isinstance(directory_metadata, dict):
        directory_metadata = [directory_metadata]
    #print(json.dumps(directory_metadata, indent=4))
    for item in directory_metadata:
        directories.append(item['@ratingKey'])
    return directories

def library_regression(app, directory_list):
        global regression_loop_count, photo_count
        for item in directory_list:
            item_metadata = API_Calls.get_item_metadata(item)['MediaContainer']
            #print(json.dumps(item_metadata, indent=4))
            photo_count += count_photos_in_metadata(item_metadata)
            print(photo_count)
            app.update_indeterminate_progressbar()
            next_directory_list = get_directories_in_metadata(item_metadata)
            if next_directory_list:
                library_regression(app, next_directory_list)
                #regression_loop_count += 1
                #print(regression_loop_count)
                #if regression_loop_count > 200:
                    #exit('Running away....')
        return photo_count

@lru_cache(maxsize=128)
def get_photo_library_count(app, key):
    global photo_count          # we need to make this global so the regression loop can access it

    # There is a special case for the top level of a section because it does have a ratingKey identifier unlike everything below it
    section_metadata = API_Calls.get_library_metadata(key)['MediaContainer']
    # Count any photos that may be in this directory
    photo_count = count_photos_in_metadata(section_metadata)
    # Create a list of directories
    directory_list = get_directories_in_metadata(section_metadata)
    app.post_to_status_console(f"Counting photos....", "info")
    app.create_progressbar("Counting Photos, This May Take Some Time....", "indeterminate")

    photo_count = library_regression(app, directory_list)
    #print(directory_list)
    app.post_to_status_console(f"Photo Count Completed.", "success")
    app.close_progressbar()
    """
    while directory_list:
        directory_key = directory_list.pop()
        directory_metadata = API_Calls.get_item_metadata(directory_key)
    """
    return photo_count

@lru_cache(maxsize=2)
def get_plex_information(app, count_photos):
    plex_info_list = []
    section_list = []
    #---------------------- PROGRAM START
    plex = API_Calls.connect_plex()                # General info
    plex_info_list.append(('Server Name', plex.friendlyName))
    plex_info_list.append(('User Name', plex.myPlexUsername))
    plex_info_list.append(('Machine ID', plex.machineIdentifier))
    plex_info_list.append(('Version', plex.platformVersion))
    plex_info_list.append(('IP Address', globals.PLEX_IP_ADDRESS))
    plex_info_list.append(('Port', globals.PLEX_PORT))
    plex_info_list.append(('Token', globals.PLEX_TOKEN))


    #--------- Create a list of all library sections for later use

    sections = API_Calls.get_library_sections()
    sections = sections['MediaContainer']['Directory']
    for section in sections:
        section_dict = {"Organization": section['scanner'], "Type": section['type'], "Title": section['title'], "Key": section['key']}
        # get the metadata for the section - prior to that you need to derive the Plex content type
        content_type = get_content_type(section_dict['Type'])
        # Special case for photos
        if section_dict['Type'] == "photo":
            if count_photos:
                count = get_photo_library_count(app, section_dict['Key'])
            else:
                count = 0
        else:
            section_metadata = API_Calls.get_metadata(section_dict['Key'], content_type, 0,0)
            count = section_metadata['MediaContainer']['totalSize']
        section_dict['Count'] = count
        section_list.append(section_dict)

    return plex_info_list, section_list

# DELETE PLAYLIST(S) ON THE PLEX SERVER
def delete_plex_playlists(app):        # Get the M3U playlists selected by the user
    selected_playlists = []
    selected_indices = app.plex_playlist_lb.curselection()
    if selected_indices:
        selected_playlists = [app.plex_playlist_lb.get(i) for i in selected_indices]
        # print(f"Selected files: {selected_playlists}")
    else:
        print("No files selected.")
        app.post_to_status_console(f"No files selected.", "error")
        return
    # Get playlist keys
    playlist_key = ""
    plex_playlists = API_Calls.get_playlists()

    for delete_playlist in selected_playlists:
        print(f"Deleting playlist: {delete_playlist}")
        app.post_to_status_console(f"Deleting playlist: {delete_playlist}", "info")
        for plex_playlist in plex_playlists:
            title = plex_playlist["title"]
            if title == delete_playlist:
                playlist_key = plex_playlist["ratingKey"]
                API_Calls.delete_playlist(playlist_key)

    app.display_plex_playlists()                # Update the plex playlist listbox to reflect any newly added playlists
    return

# PLAYLIST IMPORT TO PLEX SERVER
def get_playlists_to_import(app, working_directory):        # Get the M3U playlists selected by the user
    selected_playlists = []
    selected_indices = app.m3u_lb.curselection()
    if selected_indices:
        selected_playlists = [app.m3u_lb.get(i) for i in selected_indices]
        # print(f"Selected files: {selected_playlists}")
    else:
        print("No files selected.")
        app.post_to_status_console(f"No files selected.", "error")
        return
    for playlist in selected_playlists:
        print(f"Processing playlist: {playlist}")
        app.post_to_status_console(f"Processing playlist: {playlist}", "info")
        playlist_count, song_count = import_playlist_to_plex(app, playlist, working_directory)
        if song_count == 0:
            app.post_to_status_console(f"Playlist {playlist} not processed.", "error")
        else:
            app.post_to_status_console(f"Playlist " + playlist + " processed. " + str(song_count) + " of " + str(playlist_count) + " songs added to the new playlist.", "success")
    app.display_plex_playlists()                # Update the plex playlist listbox to reflect any newly added playlists
    return


def import_playlist_to_plex(app, playlist, working_directory):
    # Get the plex information on the target playlist
    target_library = "Music"
    library_id = ""
    library_name = ""
    library_count = 0
    plex_info, section_info = get_plex_information(app, False)
    for item in plex_info:
        if item[0] == "Machine ID":
            machine_id = item[1]
            break
    for section in section_info:
        if section['Title'] == target_library:
            library_id = section['Key']
            library_name = section['Title']
            library_count = section['Count']
            break
    if library_id == "" or library_name == "":
        print("Target library:Music not found")
        app.post_to_status_console(f"Target library:Music not found", "error")
        return 0,0
    # We now have the machine_id, library key and library name which are all used for the API calls

#------- Download the Plex music database to a local file.  Only do so if the file does not exist
    database_file = Music_Database_Import.save_music_database(app, library_name, library_id, library_count, working_directory)
    if not database_file:
        return 0,0
#------- Now find the Plex song key for each song in the new playlist
    playlist_keys = Music_Database_Import.find_playlist_keys(app, playlist, database_file, working_directory)
    if len(playlist_keys) == 0:
        print("No songs found in playlist")
        app.post_to_status_console(f"No songs found in playlist {playlist}", "error")
        return 0,0

    playlist_key = ""
    playlists= API_Calls.get_playlists()
    for plex_playlist in playlists:
        title = plex_playlist["title"]
        if title == playlist.replace(".m3u", ""):
            playlist_key = plex_playlist["ratingKey"]
            break

    if playlist_key != "":
        delete_flag = API_Calls.delete_playlist(playlist_key)
        print('Plex playlist ' + str(playlist.replace('.m3u', '')) + ' deleted')
        app.post_to_status_console(f"Plex playlist {playlist.replace('.m3u', '')} deleted on the Plex server", "info")
    new_playlist = API_Calls.create_playlist(machine_id, playlist.replace(".m3u", ""), library_id)
    new_playlist_key = new_playlist['MediaContainer']['Metadata'][0]['ratingKey']
    app.post_to_status_console(f"Plex playlist {playlist.replace('.m3u', '')} created on the Plex server.  Sending the song list.", "info")
    playlist_count, import_count= API_Calls.add_songs_to_Plex_playlist(machine_id, new_playlist_key, playlist_keys)
    if playlist_count != import_count:
        display_missing_songs(app, new_playlist_key, playlist_keys)
    return playlist_count, import_count

def display_missing_songs(app, playlist_key, playlist_keys):
    print("Some songs not accepted by Plex.  Finding out which ones were not accepted.")
    playlist_contents = API_Calls.get_playlist_contents(playlist_key)
    playlist_contents = playlist_contents['MediaContainer']['Metadata']
    for song in playlist_contents:
        if song['ratingKey'] not in playlist_keys:
            app.post_to_status_console(f"{song['title']} + not accepted by Plex", "error")
    return