# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ultimation LLC and Robert C Suffern
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import requests
import uuid
import xml.etree.ElementTree as ET  # For XML parsing, as a fallback
import globals

# Step 1: Authenticate with Plex.tv to get the auth token
def get_plex_token(user, pw, id):

    print(id)

    plex_tv_headers = {
        'X-Plex-Product': 'iTunes Playlist Import',
        'X-Plex-Version': '1.0',  # Version
        'X-Plex-Client-Identifier': id,  # Unique ID
    }

    data = {
        'user[login]': user,
        'user[password]': pw,
    }

    plex_response = requests.post('https://plex.tv/users/sign_in.json', headers=plex_tv_headers, data=data)
    #print(response.text)
    if plex_response.status_code != 201:
        raise Exception(f"Authentication failed: {plex_response.text}")

    return plex_response.json()['user']['authToken']

# Usage
def plex_login(app, username, password):

    success = False
    print("Attempting server info access")
    app.post_to_status_console("Contacting Plex.tv", "info")
    if username == "" or password == "":
        print("Username and password are required.")
        app.post_to_status_console("Username and password are required.", "error")
        return success
    print(f"Attempting login with username: {username} and password: {password}")

    client_id = str(uuid.uuid4())  # Or hardcode a persistent one
    try:
        globals.PLEX_TOKEN = get_plex_token(username, password, client_id)
        if globals.PLEX_TOKEN is None:
            app.post_to_status_console("Login to Plex.tv did not return a valid token.  Please check credentials and try again.", "error")
            return False
        else:
            app.post_to_status_console(
                "Server access token received from Plex.tv.  Adding it to Method 2 as a convenience.", "info")
            print(f"Auth token: {globals.PLEX_TOKEN}")
            app.update_token(globals.PLEX_TOKEN)        # Enter the received token into the Method 2 section as a convenience

    except Exception as e:
        #print("Login failed. Please check your credentials and try again.")
        return False
# Now ask Plex.tv for server information
    plex_server_info_url = "https://plex.tv/api/v2/resources?includeHttps=0&includeRelay=0&includeIPv6=0"
    headers = {
        'X-Plex-Token': globals.PLEX_TOKEN,
        'Accept': 'application/json',  # This header tells Plex to return JSON
        'X-Plex-Client-Identifier': client_id  # Unique ID
    }
    response = None
    local_addresses = []
    ip = ""


    try:
        response = requests.get(plex_server_info_url, headers=headers)
        response.raise_for_status()  # Check for HTTP errors
        print(f"Response Status Code: {response.status_code}")
        #print(response.text)

        content_type = response.headers.get('Content-Type', '').lower()
        print(f"Content Type: {content_type}")

        if 'json' in content_type:
            # If it's JSON, parse it
            response = response.json()
            servers = response[0].get('connections')
            #print(servers)
            local_addresses = []
            for server in servers:
                local_addresses.append(server.get("address"))
                print(f"Local Address: {server.get('address')}")

        else:  # If not reporting json
            print(f"Unexpected content type: {content_type}. Response content: {response.text[:200]}")  # Print first 200 chars for debugging
            app.post_to_status_console("Unexpected Plex.tv content type.  Check credentials and try again or, attempt Method 2 below.", "error")
            return False

    except requests.exceptions.HTTPError as err:  # Exception handling blocks
        print(f"HTTP Error occurred: {err} (Status Code: {response.status_code})")
        print(f"Response content: {response.text[:200]}")
        return False# Helpful for debugging
    except requests.exceptions.JSONDecodeError as err:
        print(f"JSON Decode Error: {err}. The response might not be JSON.")
        print(f"Response content: {response.text[:200]}")
        return False
    except requests.exceptions.RequestException as err:
        print(f"Request Error: {err}")
        app.post_to_status_console(f"Request Error: {err}", "error")
        return False


    if local_addresses == []:
        app.post_to_status_console("No local IP addresses returned by plex.tv, try using Method 2 below.")
        return success

    app.post_to_status_console(f"Plex.tv reports {len(local_addresses)} local IP Addresses", "info")

    for ip in local_addresses:
        print('Attempting IP address: ', ip)
        app.post_to_status_console(f"Attempting to connect to Plex server at {ip}", "info")
        url = f'http://{ip}:{globals.PLEX_PORT}/library/?X-Plex-Token={globals.PLEX_TOKEN}'
        print(url)

        try:
            response = requests.get(url, timeout=float(app.ip_timer.get()) / 1000)  # request fails at timeout = .3 seconds.  Using double that to start
            if response.status_code == 200:
                print(f"Plex response at  {ip} is: {response.text}")
                success = True
                break
            else:
                print(f"Plex at {ip} failed. Status code: {response.status_code}")

        except requests.exceptions.RequestException as e:
            print(f"Request Error for IP {ip}: {e}")
            app.post_to_status_console(f"Server not found", "error")

    if success:
        print(f"Plex server found at {ip} with token {globals.PLEX_TOKEN}!")
        globals.PLEX_IP_ADDRESS = ip
        app.update_ip(ip)
    else:
        print("No Plex server found at the private ip addresses provided by Plex.tv")
    return success

# check to see if the server responds using the user inputted ip address and token
def ip_login(app, ip, token):
    try:
        app.post_to_status_console(f"Attempting to connect to Plex server at {ip}", "info")

        url = f'http://{ip}:{globals.PLEX_PORT}/library/?X-Plex-Token={token}'
        print(url)

        response = requests.get(f'http://{ip}:{globals.PLEX_PORT}/library/?X-Plex-Token={token}',
                                timeout=1)  # request fails at timeout = .3 seconds.  Using double that to start
        if response.status_code == 200:
            print(f"Plex response at  {ip} is: {response.text}")
            success = True
        else:
            print(f"Plex at {ip} failed. Status code: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"Request Error for IP {ip}: {e}")
        return False

    globals.PLEX_IP_ADDRESS = ip
    globals.PLEX_TOKEN = token
    return True
#exit(555)
