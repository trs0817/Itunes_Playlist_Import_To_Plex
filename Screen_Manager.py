# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ultimation LLC and Robert C Suffern
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import os
import re
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from tkinter import filedialog, scrolledtext, messagebox
from Plex_Playlist_Import_Main import (get_plex_information, get_playlists_to_import,
                                        delete_plex_playlists, rebuild_plex_database)
from API_Calls import get_playlists, PlexConnectionError
from Plex_Login import plex_login, ip_login
import globals
import logging
from utils import resource_path

logger = logging.getLogger(__name__)
_LOG_FOR_TAG = {"info": logger.info, "warning": logger.warning,
                "error": logger.error, "success": logger.info}


class PlexImportUtility(tk.Tk):
    def __init__(self):
        super().__init__()

        # Set window/taskbar icon — works from source and when frozen by PyInstaller
        try:
            self.iconbitmap(resource_path("icon.ico"))
        except Exception as e:
            logging.getLogger(__name__).warning("Could not set window icon: %s", e)

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
        # Thread tracking and button references for disable/enable pattern
        self._worker_thread = None
        self.login_button_1 = None
        self.login_button_2 = None
        self.import_button = None
        self.rebuild_db_button = None
        self.selected_library = None   # StringVar bound to the library picker Combobox
        self.library_combo = None
        self.token = None
        self.plex_port_default_text = None
        self.plex_port = None
        self.playlist_frame = None
        self.top = None
        self.label = None
        self.progress = None

        self.m3u_folder = get_itunes_media_folder()
        logger.info("iTunes/Apple Music media folder: %s", self.m3u_folder)

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

        # add navigation tabs to each page
        m3u_notebook.add(self.login_page, text="Login to Server    ")
        m3u_notebook.add(self.import_page, text="Playlist Import   ")
        m3u_notebook.add(self.info_page, text="Plex Server Information   ")

        # Clean shutdown handler — warns if a worker thread is running
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Lock the minimum window size to whatever the layout requests
        self.after(1, lambda: self.minsize(self.winfo_reqwidth(), self.winfo_reqheight()))

        return

    # -------------------------------------------------------------------------
    # Thread helpers
    # -------------------------------------------------------------------------

    def _run_in_thread(self, target, *args, buttons=None):
        """Run target(*args) in a daemon thread.
        Disables buttons while running; re-enables them (via after()) on finish.
        Any unhandled exception is posted to the status console."""
        if buttons:
            for b in buttons:
                b.config(state="disabled")

        def _worker():
            try:
                target(*args)
            except Exception as e:
                self.after(0, self.post_to_status_console, f"Error: {e}", "error")
            finally:
                if buttons:
                    self.after(0, self._enable_buttons, buttons)

        self._worker_thread = threading.Thread(target=_worker, daemon=True)
        self._worker_thread.start()

    def _enable_buttons(self, buttons):
        for b in buttons:
            b.config(state="normal")

    @staticmethod
    def _toggle_visibility(entry, button):
        """Toggle an Entry between masked ('*') and visible."""
        if entry['show'] == '*':
            entry.config(show='')
            button.config(text='Hide')
        else:
            entry.config(show='*')
            button.config(text='Show')

    def _start_ip_login(self):
        """Validate IP and token on the main thread before starting the login thread.
        Also updates globals.PLEX_PORT from the port field."""
        # Treat placeholder values as empty
        ip = "" if getattr(self.IP_address, '_is_placeholder', False) else self.IP_address.get().strip()
        token = "" if getattr(self.token, '_is_placeholder', False) else self.token_default_text.get().strip()

        if not _is_valid_ipv4(ip):
            self.IP_address.config(
                highlightbackground="red", highlightthickness=2, highlightcolor="red")
            self.post_to_status_console(
                "Enter a valid IPv4 address (e.g. 192.168.1.100).", "error")
            return
        self.IP_address.config(highlightthickness=0)

        if len(token) < 10:
            self.post_to_status_console(
                "Enter your Plex token (Settings \u203a Account on plex.tv).", "error")
            return

        # Update port from field before connecting
        port_str = self.plex_port_default_text.get().strip() if self.plex_port_default_text else "32400"
        try:
            globals.PLEX_PORT = int(port_str) if port_str else 32400
        except ValueError:
            globals.PLEX_PORT = 32400

        self._run_in_thread(
            ip_login_process, self, ip, token,
            buttons=[self.login_button_1, self.login_button_2])

    def _start_import_with_check(self):
        """Check for overwrite conflicts on the main thread, then start import thread."""
        selected_indices = self.m3u_lb.curselection()
        if not selected_indices:
            # No selection — let get_playlists_to_import post the error
            self._run_in_thread(get_playlists_to_import, self, self.m3u_folder,
                                buttons=[self.import_button])
            return

        selected_files = [self.m3u_lb.get(i) for i in selected_indices]
        import_titles = {f.replace(".m3u8", "").replace(".m3u", "") for f in selected_files}

        existing_titles = {p['title'] for p in get_playlists()}
        overlaps = sorted(import_titles & existing_titles)

        if overlaps:
            names = "\n".join(f"  \u2022 {t}" for t in overlaps)
            if not messagebox.askyesno(
                    "Replace Existing Playlists",
                    f"These playlists already exist on Plex and will be replaced:\n\n{names}\n\nContinue?"):
                self.post_to_status_console("Import cancelled.", "info")
                return

        self._run_in_thread(get_playlists_to_import, self, self.m3u_folder,
                            buttons=[self.import_button])

    def _on_close(self):
        if self._worker_thread and self._worker_thread.is_alive():
            if not messagebox.askokcancel(
                    "Operation in Progress",
                    "An operation is still running.\nExit anyway?"):
                return
        self.destroy()

    # -------------------------------------------------------------------------
    # GUI construction
    # -------------------------------------------------------------------------

    def create_common_console(self, frame, row_index):
        ttk.Label(frame, text="Status Console:").grid(row=row_index, column=0, padx=(10, 5), pady=(2, 5), sticky='w')
        self.status_console = scrolledtext.ScrolledText(
            frame,
            wrap=tk.WORD,
            width=95,
            height=10,
            state="disabled",
            relief=tk.SOLID,
            borderwidth=2,
        )
        self.status_console.grid(row=(row_index + 1), column=0, padx=(10, 5), pady=(2, 10), sticky='sw')

        self.status_console.tag_config("info", foreground="#000000")
        self.status_console.tag_config("warning", foreground="#ffcc00")
        self.status_console.tag_config("error", foreground="#ff5555", underline=True)
        self.status_console.tag_config("success", foreground="#34eb49")
        return self.status_console

    def create_plex_login_frame(self):
        ttk.Label(self.login_page, text="To access your Plex server, choose from one of these two access methods:", font=('Arial', 10, 'bold')).grid(
            row=0, column=0, padx=10, pady=(10, 0), sticky='w')

        # Method 1 — Plex.tv login
        self.login_style = ttk.Style()
        self.login_style.configure("Grey.TFrame", background="lightgrey")

        self.login_frame = ttk.Frame(self.login_page, relief='solid', borderwidth=2, style='Grey.TFrame', padding=(5, 5))
        self.login_frame.grid(row=1, column=0, padx=5, pady=10, sticky='new')

        tk.Label(self.login_frame, text='Method 1: Connect to the Plex server using information from your Plex.tv account', bg='lightgrey').grid(
            row=0, column=0, pady=(0, 10), columnspan=3, sticky='w')
        tk.Label(self.login_frame, text='Plex Account User Name:', bg='lightgrey').grid(row=1, column=0, sticky='w')

        self.username_default_text = tk.StringVar(value="")
        self.user_name = tk.Entry(self.login_frame, textvariable=self.username_default_text, width=40)
        self.user_name.grid(row=1, column=1, padx=(24, 0), pady=(0, 10), sticky='w')

        tk.Label(self.login_frame, text='Plex Account Password:', bg='lightgrey').grid(row=2, column=0, sticky='w')

        self.password_default_text = tk.StringVar(value="")
        pwd_frame = tk.Frame(self.login_frame, bg='lightgrey')
        pwd_frame.grid(row=2, column=1, padx=(24, 0), pady=(0, 10), sticky='w')
        self.password = tk.Entry(pwd_frame, textvariable=self.password_default_text, width=37, show="*")
        self.password.pack(side=tk.LEFT)
        pwd_toggle = tk.Button(pwd_frame, text="Show", width=5,
                               command=lambda: self._toggle_visibility(self.password, pwd_toggle))
        pwd_toggle.pack(side=tk.LEFT, padx=(4, 0))

        tk.Label(self.login_frame, text='Request Timeout (msec):', bg='lightgrey').grid(row=3, column=0, padx=(0, 0), sticky='w')
        self.ip_timer_default_text = tk.StringVar(value="1000")
        vcmd = (self.register(self.validate_digits), '%P')
        self.ip_timer = tk.Entry(self.login_frame, textvariable=self.ip_timer_default_text, width=10, validate='key', validatecommand=vcmd)
        self.ip_timer.grid(row=3, column=1, padx=(24, 0), pady=(0, 10), sticky='w')

        tk.Label(self.login_frame,
                 text='Note: Only change the request timeout duration if you are having trouble connecting (increase to give more time to connect).',
                 bg='lightgrey', justify='left', font=('Arial', 10, 'italic'), wraplength=300).grid(
            padx=(10, 0), row=3, column=2, sticky='w', rowspan=2)

        self.login_button_1 = tk.Button(
            self.login_frame, text="Login",
            command=lambda: self._run_in_thread(
                plex_login_process, self,
                self.user_name.get(), self.password.get(),
                buttons=[self.login_button_1, self.login_button_2]
            )
        )
        self.login_button_1.grid(row=4, column=1, padx=(24, 0), pady=(0, 10), sticky='nw')

        # Method 2 — Direct IP / token
        self.direct_connect_style = ttk.Style()
        self.direct_connect_style.configure("Blue.TFrame", background="lightblue")

        self.direct_connect_frame = ttk.Frame(self.login_page, relief='solid', borderwidth=2, style='Blue.TFrame', padding=(5, 5))
        self.direct_connect_frame.grid(row=2, column=0, padx=5, pady=0, sticky='new')

        tk.Label(self.direct_connect_frame, text='Method 2: Connect to the Plex server using hard coded IP address and token', bg='lightblue').grid(
            row=0, column=0, pady=(0, 10), sticky='w', columnspan=2)
        tk.Label(self.direct_connect_frame, text='Plex Local IP Address:', bg='lightblue').grid(row=1, column=0, sticky='w')

        self.IP_default_text = tk.StringVar(value="")
        self.IP_address = tk.Entry(self.direct_connect_frame, textvariable=self.IP_default_text, width=40)
        self.IP_address.grid(row=1, column=1, padx=(42, 0), pady=(0, 0), sticky='w')
        _add_placeholder(self.IP_address, self.IP_default_text, "192.168.1.100")

        tk.Label(self.direct_connect_frame, text='Plex Token:', bg='lightblue').grid(row=2, column=0, sticky='w')
        self.token_default_text = tk.StringVar(value="")
        tok_frame = tk.Frame(self.direct_connect_frame, bg='lightblue')
        tok_frame.grid(row=2, column=1, padx=(42, 0), pady=(0, 0), sticky='w')
        self.token = tk.Entry(tok_frame, textvariable=self.token_default_text, width=37, show="")
        self.token.pack(side=tk.LEFT)
        tok_toggle = tk.Button(tok_frame, text="Show", width=5,
                               command=lambda: self._toggle_visibility(self.token, tok_toggle))
        tok_toggle.pack(side=tk.LEFT, padx=(4, 0))
        _add_placeholder(self.token, self.token_default_text, "Plex token", masked=True)

        self.login_button_2 = tk.Button(
            self.direct_connect_frame, text="Login",
            command=lambda: self._start_ip_login()
        )
        self.login_button_2.grid(row=3, column=1, padx=(42, 0), pady=(4, 0), sticky='w')

        tk.Label(self.direct_connect_frame, text='Plex Port:', bg='lightblue').grid(row=4, column=0, sticky='w', pady=(0, 4))
        vcmd2 = (self.register(self.validate_digits), '%P')
        self.plex_port_default_text = tk.StringVar(value="32400")
        self.plex_port = tk.Entry(self.direct_connect_frame, textvariable=self.plex_port_default_text,
                                   width=8, validate='key', validatecommand=vcmd2)
        self.plex_port.grid(row=4, column=1, padx=(42, 0), pady=(0, 4), sticky='w')

        tk.Label(self.direct_connect_frame,
                 text='Note: One way to find these values is to log onto your Plex server, select a playlist, click on Get Info for a song in the playlist, then click View XML. '
                      'The IP address is the beginning of the URL, and the token is the last value in the URL after X-Plex-Token.  Copy the token into the token field, and enter '
                      'the IP address in xxx.xxx.xxx.xxx format.',
                 bg='lightblue', justify='left', font=('Arial', 10, 'italic'), wraplength=300).grid(
            row=1, column=2, padx=(10, 0), pady=(0, 10), sticky='ne', rowspan=5, columnspan=1)
        return

    def validate_digits(self, value):
        return value.isdigit() or value == ""

    # The generic info page is made up of two frames: one for the server information and one for the library information
    def create_general_info_frame(self):
        self.info_frame = ttk.Frame(self.info_page, padding=(5, 5))
        self.info_frame.grid(row=0, column=0, padx=5, pady=10, sticky='nw')
        ttk.Label(self.info_frame, text='Server Information:').grid(row=0, column=0, sticky='w')
        ttk.Label(self.info_frame, text="Attribute:").grid(row=1, column=0, sticky='w')
        ttk.Label(self.info_frame, text="Value:").grid(row=1, column=1, sticky='w')
        self.attribute_listbox = tk.Listbox(self.info_frame, selectmode=tk.NONE, width=30, height=8)
        self.value_listbox = tk.Listbox(self.info_frame, selectmode=tk.NONE, width=50, height=8)
        self.attribute_listbox.grid(row=2, column=0, padx=(0, 0), pady=(0, 0), sticky='w')
        self.value_listbox.grid(row=2, column=1, padx=(5, 0), pady=(0, 0), sticky='w')
        copy_token_button = tk.Button(
            self.info_frame, text="Copy Token to Clipboard",
            command=lambda: (self.clipboard_clear(), self.clipboard_append(globals.PLEX_TOKEN))
        )
        copy_token_button.grid(row=3, column=1, padx=(5, 0), pady=(5, 0), sticky='w')
        return

    def create_library_info_frame(self):
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
        import_frame = ttk.Frame(self.import_page, padding=(5, 5))
        import_frame.grid(row=0, column=0, padx=5, pady=10, sticky='nw')

        tk.Label(import_frame, text="iTunes Playlist (*.M3U) File Location:").grid(row=0, column=0, padx=(0, 10), sticky='w')
        browse_button = tk.Button(import_frame, text="Browse", command=lambda: self.browse_m3u_folder())
        browse_button.grid(row=0, column=1, columnspan=1, sticky='e', padx=(0, 10), pady=(0, 0))

        self.folder_text = tk.StringVar(value=str(self.m3u_folder))
        m3u_folder = tk.Entry(import_frame, textvariable=self.folder_text, width=63)
        m3u_folder.grid(row=0, column=2, sticky='w')

        tk.Label(import_frame, text="Target Music Library:").grid(row=1, column=0, padx=(0, 10), pady=(4, 0), sticky='w')
        self.selected_library = tk.StringVar(value="")
        self.library_combo = ttk.Combobox(import_frame, textvariable=self.selected_library,
                                          state='readonly', width=40)
        self.library_combo.grid(row=1, column=2, pady=(4, 0), sticky='w')
        self.playlist_frame = ttk.Frame(self.import_page, padding=(5, 5))
        self.playlist_frame.grid(row=1, column=0, padx=5, pady=0, sticky='nw')
        ttk.Label(self.playlist_frame, text="M3U (iTunes Exported) Playlist Files:").grid(row=0, column=0, padx=(0, 10), sticky='w')
        ttk.Label(self.playlist_frame, text="Plex Playlists:").grid(row=0, column=1, sticky='w')

        self.m3u_lb = tk.Listbox(self.playlist_frame, selectmode=tk.MULTIPLE, width=62, height=10)
        self.m3u_lb.grid(row=1, column=0, padx=(0, 5), pady=(0, 5), sticky='w')

        self.plex_playlist_lb = tk.Listbox(self.playlist_frame, selectmode=tk.MULTIPLE, width=62, height=10)
        self.plex_playlist_lb.grid(row=1, column=1, padx=(0, 5), pady=(0, 5), sticky='w')

        tk.Label(self.playlist_frame, text="Select Playlist(s) to Import").grid(row=2, column=0, padx=(0, 5), sticky='w')
        self.import_button = tk.Button(
            self.playlist_frame, text="Import to Plex",
            command=lambda: self._start_import_with_check()
        )
        self.import_button.grid(row=3, column=0, sticky='w', padx=(0, 5), pady=(0, 0))

        tk.Label(self.playlist_frame, text="Select Plex Playlist(s) to Delete").grid(row=2, column=1, padx=(0, 5), sticky='w')
        delete_button = tk.Button(self.playlist_frame, text="Delete Playlist(s)",
                                  command=lambda: delete_plex_playlists(self))
        delete_button.grid(row=3, column=1, sticky='w', padx=(0, 5), pady=(0, 0))
        self.rebuild_db_button = tk.Button(
            self.playlist_frame, text="Rebuild Music Database",
            command=lambda: self._run_in_thread(
                rebuild_plex_database, self,
                buttons=[self.rebuild_db_button]
            )
        )
        self.rebuild_db_button.grid(row=4, column=0, sticky='w', padx=(0, 5), pady=(4, 0))
        return

    def browse_m3u_folder(self):
        new_m3u_folder = filedialog.askdirectory(title="Select M3U Folder", initialdir=self.m3u_folder)
        if new_m3u_folder:
            logger.info("M3U folder selected: %s", new_m3u_folder)
            self.m3u_folder = Path(new_m3u_folder)
            self.folder_text.set(new_m3u_folder)
            self.display_m3u_files(self.m3u_folder)
        else:
            logger.debug("No folder selected in dialog")
        return

    def display_m3u_files(self, m3u_folder):
        self.m3u_lb.delete(0, tk.END)
        files = os.listdir(m3u_folder)
        for file in files:
            if file.endswith('.m3u') or file.endswith('.m3u8'):
                self.m3u_lb.insert(tk.END, file)
        return

    def display_plex_playlists(self):
        # Called from background thread via after() — safe to touch widgets here
        playlists = get_playlists()
        self.plex_playlist_lb.delete(0, tk.END)
        for playlist in playlists:
            self.plex_playlist_lb.insert(tk.END, playlist['title'])
        return

    # -------------------------------------------------------------------------
    # Thread-safe UI update methods
    # -------------------------------------------------------------------------

    def post_to_status_console(self, message, tag="info"):
        """Post a message to all status consoles. Thread-safe: marshals to the
        main thread via after() when called from a worker thread."""
        if threading.current_thread() is threading.main_thread():
            self._do_post_console(message, tag)
        else:
            self.after(0, self._do_post_console, message, tag)

    def _do_post_console(self, message, tag="info"):
        _LOG_FOR_TAG.get(tag, logger.info)("[GUI] %s", message)
        for console in self.console_list:
            console.config(state="normal")
            console.insert(tk.END, f"{message}\n", tag)
            console.see(tk.END)
            console.config(state="disabled")

    def update_info_screen(self, photo_flag):
        if globals.PLEX_IP_ADDRESS == "":
            self.post_to_status_console("Plex not connected.  Please log onto your server using the Login to Server tab.", "error")
            return
        else:
            try:
                plex_info, library_info = get_plex_information(self, photo_flag)
                self.post_to_status_console("Plex Server Information Retrieved", "info")
                initialize_screen_data(self, plex_info, library_info)
            except PlexConnectionError as e:
                self.post_to_status_console(f"Connection error: {e}", "error")

    def create_progressbar(self, text, mode):
        """Create the progress-bar popup. Thread-safe."""
        if threading.current_thread() is not threading.main_thread():
            self.after(0, self._do_create_progressbar, text, mode)
        else:
            self._do_create_progressbar(text, mode)

    def _do_create_progressbar(self, text, mode):
        self.top = tk.Toplevel(self)
        self.top.title(text)
        self.top.geometry("420x150+100+100")
        self.label = tk.Label(self.top, text="Processing...")
        self.label.pack(padx=20, pady=10)
        self.progress = ttk.Progressbar(self.top, mode=mode)
        self.progress.pack(padx=20, pady=10, fill="x")
        if mode == "indeterminate":
            self.progress.start(100)

    def update_progressbar(self, value):
        """Update determinate progress bar. Thread-safe fire-and-forget."""
        if threading.current_thread() is not threading.main_thread():
            self.after(0, self._do_update_progressbar, value)
        else:
            self._do_update_progressbar(value)

    def _do_update_progressbar(self, value):
        if self.progress is not None:
            self.progress['value'] = value

    def update_indeterminate_progressbar(self):
        """No-op from a background thread; the indeterminate bar spins on its own."""
        pass

    def close_progressbar(self):
        """Close the progress-bar popup. Thread-safe."""
        if threading.current_thread() is not threading.main_thread():
            self.after(0, self._do_close_progressbar)
        else:
            self._do_close_progressbar()

    def _do_close_progressbar(self):
        if self.top is not None:
            self.top.destroy()
            self.top = None
            self.progress = None

    def update_token(self, token):
        """Set the token field from code (bypasses placeholder)."""
        self.token_default_text.set(token)
        self.token.config(fg="black", show="*")
        self.token._is_placeholder = False

    def update_ip(self, ip):
        """Set the IP field from code (bypasses placeholder)."""
        self.IP_default_text.set(ip)
        self.IP_address.config(fg="black")
        self.IP_address._is_placeholder = False

    def populate_library_picker(self, section_info):
        """Populate the Target Music Library combobox from section_info after login.
        Filters to sections with Type == 'artist' (Plex's music library type)."""
        music_sections = [s for s in section_info if s.get('Type') == 'artist']
        titles = [s['Title'] for s in music_sections]
        self.library_combo['values'] = titles
        if not titles:
            self.selected_library.set("")
            self.post_to_status_console(
                "No music libraries found on this server.", "warning")
        elif len(titles) == 1:
            self.selected_library.set(titles[0])
        else:
            default = "Music" if "Music" in titles else titles[0]
            self.selected_library.set(default)

#   CLASS DEFINITION ENDS HERE


def _add_placeholder(entry, string_var, placeholder: str, masked: bool = False):
    """Bind lightweight placeholder behaviour to an Entry widget.

    When the field is empty and unfocused, it shows `placeholder` in grey.
    On focus-in the placeholder is cleared and the entry is ready for input.
    For masked fields (token), show='' during placeholder, show='*' while typing.
    Sets entry._is_placeholder = True/False so callers can detect the state.
    """
    string_var.set(placeholder)
    entry.config(fg="grey")
    entry._is_placeholder = True

    def _focus_in(event):
        if entry._is_placeholder:
            string_var.set("")
            entry.config(fg="black")
            if masked:
                entry.config(show="*")
            entry._is_placeholder = False

    def _focus_out(event):
        if not string_var.get():
            if masked:
                entry.config(show="")
            string_var.set(placeholder)
            entry.config(fg="grey")
            entry._is_placeholder = True

    entry.bind("<FocusIn>", _focus_in)
    entry.bind("<FocusOut>", _focus_out)

def _is_valid_ipv4(ip: str) -> bool:
    """Return True if ip is a syntactically valid IPv4 address (each octet 0-255)."""
    m = re.fullmatch(r'(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})', ip)
    return bool(m) and all(0 <= int(g) <= 255 for g in m.groups())

# this is the main startup process.  Stay here until a successful login and then update the info and playlist screens
def ip_login_process(scr_root, ip, token):
    success = ip_login(scr_root, ip, token)
    if not success:
        scr_root.post_to_status_console("The server was not found.  Please check credentials and try again.", "error")
        return
    scr_root.post_to_status_console("Login Successful", "success")
    scr_root.after(0, scr_root.update_info_screen, False)
    m3u_path = get_itunes_media_folder()
    scr_root.after(0, scr_root.display_m3u_files, m3u_path)
    scr_root.after(0, scr_root.display_plex_playlists)
    return


def plex_login_process(scr_root, username, password):
    success = plex_login(scr_root, username, password)
    if not success:
        scr_root.post_to_status_console("Server access Failed.  Please check credentials and try again, or attempt Method 2 below.", "error")
        return
    scr_root.post_to_status_console("Login Successful", "success")
    scr_root.after(0, scr_root.update_info_screen, False)
    m3u_path = get_itunes_media_folder()
    scr_root.after(0, scr_root.display_m3u_files, m3u_path)
    scr_root.after(0, scr_root.display_plex_playlists)
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
    scr_root.populate_library_picker(library_info)
    return


def get_itunes_media_folder():              # Get as close as you can to the playlist export folder
    home = Path.home()
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
