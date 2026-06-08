# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ultimation LLC and Robert C Suffern
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import os
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from tkinter import filedialog, scrolledtext, messagebox
from Plex_Playlist_Import_Main import get_plex_information, get_playlists_to_import, delete_plex_playlists
from API_Calls import get_playlists
from Plex_Login import plex_login, ip_login
import globals

class PlexImportUtility(tk.Tk):
    def __init__(self):
        super().__init__()

        # variable declarations
        self.library_count_lb = None
        self.library_key_lb = None
        self.library_id_lb = None
        self.library_type_lb = None
        self.library_org_lb = None
        self.info_frame = None
        self.attribute_listbox = None
        self.value_listbox = None
        self.m3u_lb = None
        self.folder_text = None
        self.plex_playlist_lb = None
        self.status_console = None
        self.login_style = None
        self.login_frame = None
        self.username_default_text = None
        self.user_name = None
        self.password_default_text = None
        self.password = None
        self.ip_timer = None
        self.ip_timer_default_text = None
        self.direct_connect_style = None
        self.direct_connect_frame = None
        self.IP_default_text = None
        self.IP_address = None
        self.token_default_text = None
        self.token = None
        self.playlist_frame = None
        self.top = None
        self.label = None
        self.progress = None





        self.m3u_folder = get_itunes_media_folder()
        print(f"iTunes/Apple Music media folder: {self.m3u_folder}")

        self.title('Plex M3U Playlist Import Utility')

        m3u_notebook = ttk.Notebook(self)
        m3u_notebook.pack(expand=1, fill='both')

        self.login_page = ttk.Frame(m3u_notebook)
        self.create_plex_login_frame()
        self.login_page.pack(expand=1, fill='both')

        self.info_page = ttk.Frame(m3u_notebook)
        self.create_general_info_frame()
        self.create_library_info_frame()
        self.info_page.pack(expand=1, fill='both')

        self.import_page = ttk.Frame(m3u_notebook)
        self.create_import_frame()
        self.import_page.pack(expand=1, fill='both')

        # Add row configuration here
        self.login_page.grid_rowconfigure(0, weight=0)
        self.login_page.grid_rowconfigure(1, weight=0)
        self.login_page.grid_rowconfigure(2, weight=1)
        self.login_page.grid_rowconfigure(3, weight=0)
        self.login_page.grid_rowconfigure(4, weight=0)


        self.login_page.grid_columnconfigure(0, weight=1)

        self.import_page.grid_rowconfigure(0, weight=0)
        self.import_page.grid_rowconfigure(1, weight=1)
        self.import_page.grid_rowconfigure(2, weight=0)
        self.import_page.grid_rowconfigure(3, weight=0)

        self.info_page.grid_rowconfigure(0, weight=1)
        self.info_page.grid_rowconfigure(1, weight=1)
        self.info_page.grid_rowconfigure(2, weight=0)
        self.info_page.grid_rowconfigure(3, weight=0)

        # Add a status console to each of the three pages
        self.import_console = self.create_common_console(self.import_page, 2)
        self.info_console = self.create_common_console(self.info_page, 2)
        self.login_console = self.create_common_console(self.login_page, 3)

        self.console_list = [self.import_console, self.info_console, self.login_console]

        # Frames created now populate the data
        #self.post_to_status_console("Program Start", "info")
        #self.update_info_screen(False)

        # add navigation tabs to each page
        m3u_notebook.add(self.login_page, text="Login to Server    ")
        m3u_notebook.add(self.import_page, text="Playlist Import   ")
        m3u_notebook.add(self.info_page, text="Plex Server Information   ")

        return

    def create_common_console(self, frame, row_index):
        ttk.Label(frame, text="Status Console:").grid(row=row_index, column=0, padx=(10, 5), pady=(2, 5), sticky='w')
        # Create a scrolled text box to display the log output from the import process
        self.status_console = scrolledtext.ScrolledText(
            frame,  # ← replace with your target frame
            wrap=tk.WORD,  # or tk.NONE if you want horizontal scrollbar too
            width=95,
            height=10,
            state="disabled",
            relief=tk.SOLID,
            borderwidth=2,
            # start read-only
        )
        self.status_console.grid(row=(row_index+1), column=0, padx=(10, 5), pady=(2, 10), sticky='sw')

        # Optional: nicer look for different kinds of messages
        self.status_console.tag_config("info", foreground="#000000")
        self.status_console.tag_config("warning", foreground="#ffcc00")
        self.status_console.tag_config("error", foreground="#ff5555", underline=True)
        self.status_console.tag_config("success", foreground="#34eb49")
        return self.status_console

    def create_plex_login_frame(self):
        ttk.Label(self.login_page, text="To access your Plex server, choose from one of these two access methods:", font=('Arial', 10, 'bold')).grid(row=0, column=0, padx=10, pady=(10, 0),
                                                                       sticky='w')

        # The first frame is a method to log into PLex.tv to get IP address and token
        self.login_style = ttk.Style()
        self.login_style.configure("Grey.TFrame", background="lightgrey")

        self.login_frame = ttk.Frame(self.login_page, relief='solid', borderwidth=2, style='Grey.TFrame', padding=(5, 5))
        self.login_frame.grid(row=1, column=0, padx=5, pady=10, sticky='new')

        tk.Label(self.login_frame, text='Method 1: Connect to the Plex server using information from your Plex.tv account', bg='lightgrey').grid(row=0, column=0, pady=(0,10), columnspan=3,sticky='w')
        tk.Label(self.login_frame, text='Plex Account User Name:', bg='lightgrey').grid(row=1, column=0, sticky='w')

        self.username_default_text = tk.StringVar(value="")
        self.user_name = tk.Entry(self.login_frame, textvariable=self.username_default_text, width=40)
        self.user_name.grid(row=1, column=1, padx=(24, 0), pady=(0, 10), sticky='w')

        tk.Label(self.login_frame, text='Plex Account Password:', bg='lightgrey').grid(row=2, column=0, sticky='w')

        self.password_default_text = tk.StringVar(value="")
        self.password = tk.Entry(self.login_frame, textvariable=self.password_default_text, width=40)
        self.password.grid(row=2, column=1, padx=(24, 0), pady=(0, 10), sticky='w')

        tk.Label(self.login_frame, text='Request Timeout (msec):', bg='lightgrey').grid(row=3, column=0, padx=(0,0), sticky='w')
        self.ip_timer_default_text = tk.StringVar(value="1000")
        vcmd = (self.register(self.validate_digits), '%P')
        self.ip_timer = tk.Entry(self.login_frame, textvariable=self.ip_timer_default_text, width=10, validate='key', validatecommand=vcmd)

        self.ip_timer.grid(row=3, column=1, padx=(24, 0), pady=(0, 10), sticky='w')
        tk.Label(self.login_frame, text='Note: Only change the request timeout duration if you are having trouble connecting (increase to give more time to connect).', bg='lightgrey',justify='left',font=('Arial', 10, 'italic'), wraplength=300).grid(
            padx=(10,0),
            row=3, column=2,
            sticky='w',
            rowspan=2)

        login_button = tk.Button(self.login_frame, text="Login", command=lambda: plex_login_process(self, self.user_name.get(), self.password.get()))
        login_button.grid(row=4, column=1, padx=(24, 0), pady=(0, 10), sticky='nw')

        #------------------------------------------------------------------------------------------------------------------------------------------------------------
        # The second frame is a method to directly enter the local IP address of the server as well as the token, which can be found in the URL request to the server
        self.direct_connect_style = ttk.Style()
        self.direct_connect_style.configure("Blue.TFrame", background="lightblue")

        self.direct_connect_frame = ttk.Frame(self.login_page, relief='solid', borderwidth=2, style='Blue.TFrame', padding=(5, 5))
        self.direct_connect_frame.grid(row=2, column=0, padx=5, pady=0, sticky='new')

        tk.Label(self.direct_connect_frame, text='Method 2: Connect to the Plex server using hard coded IP address and token', bg='lightblue').grid(row=0, column=0,
                                                                                                        pady=(0, 10),
                                                                                                        sticky='w',
                                                                                                        columnspan=2)
        tk.Label(self.direct_connect_frame, text='Plex Local IP Address:', bg='lightblue').grid(row=1, column=0, sticky='w')

        self.IP_default_text = tk.StringVar(value="")
        self.IP_address = tk.Entry(self.direct_connect_frame, textvariable=self.IP_default_text, width=40)
        self.IP_address.grid(row=1, column=1, padx=(42, 0), pady=(0, 0), sticky='w')

        tk.Label(self.direct_connect_frame, text='Plex Token:', bg='lightblue').grid(row=2, column=0, sticky='w')
        self.token_default_text = tk.StringVar(value="")
        self.token = tk.Entry(self.direct_connect_frame, textvariable=self.token_default_text, width=40)
        self.token.grid(row=2, column=1, padx=(42, 0), pady=(0, 0), sticky='w')

        login_button = tk.Button(self.direct_connect_frame, text="Login",
                                 command=lambda: ip_login_process(self, self.IP_address.get(), self.token.get()))
        login_button.grid(row=3, column=1, padx=(42, 0), pady=(0, 0), sticky='w')

        tk.Label(self.direct_connect_frame,
                 text='Note: One way to find these values is to log onto your Plex server, select a playlist, click on Get Info for a song in the playlist, then click View XML. '
                      'The IP address is the beginning of the URL, and the token is the last value in the URL after X-Plex-Token.  Copy the token into the token field, and enter '
                      'the IP address in xxx.xxx.xxx.xxx format.', bg='lightblue',justify='left',font=('Arial', 10, 'italic'), wraplength=300).grid(
            row=1, column=2,
            padx=(10,0),
            pady=(0, 10),
            sticky='ne',
            rowspan=4,
            columnspan=1)
        return

    @staticmethod
    def validate_digits(self, value):
        return value.isdigit() or value == ""

# The generic info page is made up of two frames: one for the server information and one for the library information
    def create_general_info_frame(self):
        # This frame will contain generic server information
        self.info_frame = ttk.Frame(self.info_page, padding=(5, 5))
        self.info_frame.grid(row=0, column=0, padx=5, pady=10, sticky='nw')
        ttk.Label(self.info_frame, text='Server Information:').grid(row=0, column=0, sticky='w')
        ttk.Label(self.info_frame, text="Attribute:").grid(row=1, column=0, sticky='w')
        ttk.Label(self.info_frame, text="Value:").grid(row=1, column=1, sticky='w')
        self.attribute_listbox = tk.Listbox(self.info_frame, selectmode=tk.NONE, width=30, height=8)
        self.value_listbox = tk.Listbox(self.info_frame, selectmode=tk.NONE, width=50, height=8)
        self.attribute_listbox.grid(row=2, column=0, padx=(0, 0), pady=(0, 0), sticky='w')
        self.value_listbox.grid(row=2, column=1, padx=(5, 0), pady=(0, 0), sticky='w')
        return


    def create_library_info_frame(self):
        # This frame contains information on the Plex libraries on the server
        library_frame = ttk.Frame(self.info_page, padding=(5, 0))
        library_frame.grid(row=1, column=0, padx=5, pady=0, sticky='nw')

        ttk.Label(library_frame, text="Library Information:").grid(row=0, column=0, sticky='w')
        ttk.Label(library_frame, text="Organization:").grid(row=1, column=0, sticky='w')
        ttk.Label(library_frame, text="Type:").grid(row=1, column=1, sticky='w')
        ttk.Label(library_frame, text="Title:").grid(row=1, column=2, sticky='w')
        ttk.Label(library_frame, text="Key:").grid(row=1, column=3, sticky='w')
        ttk.Label(library_frame, text="Item Count:").grid(row=1, column=4, sticky='w')

        self.library_org_lb = tk.Listbox(library_frame, selectmode=tk.NONE, width=30, height=7)
        self.library_type_lb = tk.Listbox(library_frame, selectmode=tk.NONE, width=20, height=7)
        self.library_id_lb = tk.Listbox(library_frame, selectmode=tk.NONE, width=30, height=7)
        self.library_key_lb = tk.Listbox(library_frame, selectmode=tk.NONE, width=20, height=7)
        self.library_count_lb = tk.Listbox(library_frame, selectmode=tk.NONE, width=20, height=7)

        self.library_org_lb.grid(row=2, column=0, sticky='w', padx=(0, 5), pady=(0, 10))
        self.library_type_lb.grid(row=2, column=1, sticky='w', padx=(0, 5), pady=(0, 10))
        self.library_id_lb.grid(row=2, column=2, sticky='w', padx=(0, 5), pady=(0, 10))
        self.library_key_lb.grid(row=2, column=3, sticky='w', padx=(0, 5), pady=(0, 10))
        self.library_count_lb.grid(row=2, column=4, sticky='w', padx=(0, 10), pady=(0, 10))

        photo_count_button = tk.Button(library_frame, text="Get Photo Count",
                                       command=lambda: self.update_info_screen(True))
        photo_count_button.grid(row=3, column=4, columnspan=1, sticky='w', pady=(0, 10))
        return

    # This page contains the playlist import logic, a list of M3U files, a list of playlists on the plex server
    def create_import_frame(self):
        # This is the second page of the notebook which lists the m3u files in the specified folder and then allows you to select which ones to import
        import_frame = ttk.Frame(self.import_page, padding=(5, 5))
        import_frame.grid(row=0, column=0, padx=5, pady=10, sticky='nw')

        tk.Label(import_frame, text="iTunes Playlist (*.M3U) File Location:").grid(row=0, column=0,padx=(0,10), sticky='w')
        browse_button = tk.Button(import_frame, text="Browse", command=lambda: self.browse_m3u_folder())
        browse_button.grid(row=0, column=1, columnspan=1, sticky='e', padx=(0,10), pady=(0, 0))

        self.folder_text = tk.StringVar(value=str(self.m3u_folder))
        m3u_folder = tk.Entry(import_frame, textvariable=self.folder_text, width=63)
        m3u_folder.grid(row=0, column=2,  sticky='w')

        self.playlist_frame = ttk.Frame(self.import_page, padding=(5, 5))
        self.playlist_frame.grid(row=1, column=0, padx=5, pady=0, sticky='nw')
        ttk.Label(self.playlist_frame, text="M3U (iTunes Exported) Playlist Files:").grid(row=0, column=0, padx=(0,10), sticky='w')
        ttk.Label(self.playlist_frame, text="Plex Playlists:").grid(row=0, column=1, sticky='w')


        self.m3u_lb = tk.Listbox(self.playlist_frame, selectmode=tk.MULTIPLE, width= 62, height=10)
        self.m3u_lb.grid(row=1, column=0, padx=(0,5), pady=(0, 5), sticky='w')
        #self.display_m3u_files(self.m3u_folder)

        self.plex_playlist_lb = tk.Listbox(self.playlist_frame, selectmode=tk.MULTIPLE, width=62, height=10)
        self.plex_playlist_lb.grid(row=1, column=1, padx=(0,5), pady=(0,5), sticky='w')
        #self.display_plex_playlists()

        tk.Label(self.playlist_frame, text="Select Playlist(s) to Import").grid(row=2, column=0, padx=(0, 5), sticky='w')
        import_button = tk.Button(self.playlist_frame, text="Import to Plex",
                                  command=lambda: get_playlists_to_import(self, self.m3u_folder))
        import_button.grid(row=3, column=0, sticky='w', padx=(0, 5), pady=(0, 0))

        tk.Label(self.playlist_frame, text="Select Plex Playlist(s) to Delete").grid(row=2, column=1, padx=(0, 5), sticky='w')
        import_button = tk.Button(self.playlist_frame, text="Delete Playlist(s)",
                                  command=lambda: delete_plex_playlists(self))
        import_button.grid(row=3, column=1, sticky='w', padx=(0, 5), pady=(0, 0))
        return

    def browse_m3u_folder(self):
        # This function opens a file dialog to allow the user to select a folder containing m3u files
        new_m3u_folder = filedialog.askdirectory(
            title="Select M3U Folder",
            initialdir=self.m3u_folder,)
        if new_m3u_folder:
            print(f"Selected folder: {new_m3u_folder}")
            self.m3u_folder = Path(new_m3u_folder)
            self.folder_text.set(new_m3u_folder)
            self.display_m3u_files(self.m3u_folder)
        else:
            print("No folder selected.")
        return

    def display_m3u_files(self, m3u_folder):
        # This function updates the listbox to display the m3u files in the specified folder
        self.m3u_lb.delete(0, tk.END)
        files = os.listdir(m3u_folder)
        for file in files:
            if file.endswith('.m3u'):
                self.m3u_lb.insert(tk.END, file)
        return

    def display_plex_playlists(self):
        playlists = get_playlists()
        self.plex_playlist_lb.delete(0, tk.END)
        for playlist in playlists:
            self.plex_playlist_lb.insert(tk.END, playlist['title'])
        return

    def post_to_status_console(self, message, tag="info"):
        for console in self.console_list:
            console.config(state="normal")
            console.insert(tk.END, f"{message}\n", tag)
            console.see(tk.END)
            console.config(state="disabled")
            console.update_idletasks()
        return

    def update_info_screen(self, photo_flag):
        if globals.PLEX_IP_ADDRESS == "":
            self.post_to_status_console("Plex not connected.  Please log onto your server using the Login to Server tab.", "error")
            return
        else:
            plex_info, library_info = get_plex_information(self, photo_flag)
            self.post_to_status_console(f"Plex Server Information Retrieved", "info")
            initialize_screen_data(self, plex_info, library_info)
            return

    def music_database_create_mb(self):
        result = messagebox.askokcancel("Confirm", "Create Music Database?")
        if result:
            self.post_to_status_console("Music database creation confirmed", "info")
        else:
            self.post_to_status_console("Music database creation cancelled", "info")
        return result

    def create_progressbar(self, text, mode):
        self.top = tk.Toplevel(self)
        self.top.title(text)
        self.top.geometry("420x150+100+100")  # Set size

        # Label
        self.label = tk.Label(self.top, text="Processing...")
        self.label.pack(padx=20, pady=10)

        # Progress bar
        self.progress = ttk.Progressbar(self.top, mode=mode)
        self.progress.pack(padx=20, pady=10, fill="x")
        if mode == "indeterminate":
            self.progress.start(100)
        self.top.update()
        return

    def update_progressbar(self, value):
        self.progress['value'] = value
        self.top.update()
        return

    def update_indeterminate_progressbar(self):
        self.top.update()
        return

    def close_progressbar(self):
        self.top.destroy()

    def update_token(self, token):
        self.token_default_text.set(token)
        return

    def update_ip(self, ip):
        self.IP_default_text.set(ip)
        return
#   CLASS DEFINITION ENDS HERE

# this is the main startup process.  Stay here until a successful login and then update the info and playlist screens
def ip_login_process(scr_root, ip, token):
    success = ip_login(scr_root, ip, token)
    if not success:
        scr_root.post_to_status_console("The server was not found.  Please check credentials and try again.", "error")
        return
    scr_root.post_to_status_console("Login Successful", "success")
    scr_root.update_info_screen(False)
    m3u_path = get_itunes_media_folder()
    scr_root.display_m3u_files(m3u_path)
    scr_root.display_plex_playlists()
    return

def plex_login_process(scr_root, username, password):
    success = plex_login(scr_root, username, password)
    if not success:
        scr_root.post_to_status_console("Server access Failed.  Please check credentials and try again, or attempt Method 2 below.", "error")
        return
    scr_root.post_to_status_console("Login Successful", "success")
    scr_root.update_info_screen(False)
    m3u_path = get_itunes_media_folder()
    scr_root.display_m3u_files(m3u_path)
    scr_root.display_plex_playlists()
    return

def initialize_screen_data(scr_root, plex_info, library_info):
    scr_root.attribute_listbox.delete(0, tk.END)
    scr_root.value_listbox.delete(0, tk.END)
    scr_root.library_org_lb.delete(0, tk.END)
    scr_root.library_type_lb.delete(0, tk.END)
    scr_root.library_id_lb.delete(0, tk.END)
    scr_root.library_key_lb.delete(0, tk.END)
    scr_root.library_count_lb.delete(0, tk.END)

    for item in plex_info:
        scr_root.attribute_listbox.insert(tk.END, item[0])
        scr_root.value_listbox.insert(tk.END, item[1])

    for item in library_info:
        scr_root.library_org_lb.insert(tk.END, item['Organization'])
        scr_root.library_type_lb.insert(tk.END, item['Type'])
        scr_root.library_id_lb.insert(tk.END, item['Title'])
        scr_root.library_key_lb.insert(tk.END, item['Key'])
        scr_root.library_count_lb.insert(tk.END, item['Count'])
    return

def get_itunes_media_folder():              # Get as close as you can to the playlist export folder
    home = Path.home()
    # Prioritized list of potential paths
    search_paths = [
        home / "Music" / "iTunes" / "Playlist Export",
        home / "Music" / "iTunes",
        home / "Music",
        home
    ]
    for path in search_paths:
        if path.exists():
            return path
    return Path("C:/")