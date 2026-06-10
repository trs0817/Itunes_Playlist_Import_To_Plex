# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ultimation LLC and Robert C Suffern
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import requests
import uuid
import xml.etree.ElementTree as ET  # For XML parsing, as a fallback
import globals
import logging
logger = logging.getLogger(__name__)

# Step 1: Authenticate with Plex.tv to get the auth token
def get_plex_token(user, pw, id):

    logger.debug("Content type id: %s", id)

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
    logger.info("Attempting server info access")
    app.post_to_status_console("Contacting Plex.tv", "info")
    if username == "" or password == "":
        logger.warning("Username and password are required")
        app.post_to_status_console("Username and password are required.", "error")
        return success

    client_id = str(uuid.uuid4())  # Or hardcode a persistent one
    try:
        globals.PLEX_TOKEN = get_plex_token(username, password, client_id)
        if globals.PLEX_TOKEN is None:
            app.post_to_status_console("Login to Plex.tv did not return a valid token.  Please check credentials and try again.", "error")
            return False
        else:
            app.post_to_status_console(
                "Server access token received from Plex.tv.  Adding it to Method 2 as a convenience.", "info")
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
        logger.debug("Response status: %s", response.status_code)
        #print(response.text)

        content_type = response.headers.get('Content-Type', '').lower()
        logger.debug("Content type: %s", content_type)

        if 'json' in content_type:
            # If it's JSON, parse it
            response = response.json()
            servers = response[0].get('connections')
            #print(servers)
            local_addresses = []
            for server in servers:
                local_addresses.append(server.get("address"))
                logger.info("Local address: %s", server.get('address'))

        else:  # If not reporting json
            logger.warning("Unexpected content type: %s", content_type)  # Response content omitted (may contain token)
            app.post_to_status_console("Unexpected Plex.tv content type.  Check credentials and try again or, attempt Method 2 below.", "error")
            return False

    except requests.exceptions.HTTPError as err:  # Exception handling blocks
        logger.error("HTTP error: %s (status %s)", err, response.status_code)
        logger.debug("Response snippet: %s", response.text[:200])
        return False# Helpful for debugging
    except requests.exceptions.JSONDecodeError as err:
        logger.error("JSON decode error: %s", err)
        logger.debug("Response snippet: %s", response.text[:200])
        return False
    except requests.exceptions.RequestException as err:
        logger.error("Request error: %s", err)
        app.post_to_status_console(f"Request Error: {err}", "error")
        return False


    if local_addresses == []:
        app.post_to_status_console("No local IP addresses returned by plex.tv, try using Method 2 below.")
        return success

    app.post_to_status_console(f"Plex.tv reports {len(local_addresses)} local IP Addresses", "info")

    for ip in local_addresses:
        logger.info("Attempting IP address: %s", ip)
        app.post_to_status_console(f"Attempting to connect to Plex server at {ip}", "info")
        url = f'http://{ip}:{globals.PLEX_PORT}/library/'
        scan_headers = {'X-Plex-Token': globals.PLEX_TOKEN, 'Accept': 'application/json'}

        try:
            response = requests.get(url, headers=scan_headers, timeout=float(app.ip_timer.get()) / 1000)
            if response.status_code == 200:
                logger.debug("Plex response at %s: status %s", ip, response.status_code)
                success = True
                break
            else:
                logger.warning("Plex at %s failed, status %s", ip, response.status_code)

        except requests.exceptions.RequestException as e:
            logger.warning("Request error for IP %s: %s", ip, e)
            app.post_to_status_console(f"Server not found", "error")

    if success:
        globals.PLEX_IP_ADDRESS = ip
        app.update_ip(ip)
    else:
        logger.warning("No Plex server found at any private IP address from Plex.tv")
    return success

# check to see if the server responds using the user inputted ip address and token
def ip_login(app, ip, token):
    try:
        app.post_to_status_console(f"Attempting to connect to Plex server at {ip}", "info")

        url = f'http://{ip}:{globals.PLEX_PORT}/library/'
        ip_headers = {'X-Plex-Token': token, 'Accept': 'application/json'}
        response = requests.get(url, headers=ip_headers, timeout=1)
        if response.status_code == 200:
            logger.debug("Plex response at %s: status %s", ip, response.status_code)
            success = True
        else:
            logger.warning("Plex at %s failed, status %s", ip, response.status_code)
            return False
    except requests.exceptions.RequestException as e:
        logger.warning("Request error for IP %s: %s", ip, e)
        return False

    globals.PLEX_IP_ADDRESS = ip
    globals.PLEX_TOKEN = token
    return True
#exit(555)
