# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ultimation LLC and Robert C Suffern
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

__author__ = 'RCS'

from Screen_Manager import PlexImportUtility


if __name__ == '__main__':
    app = PlexImportUtility()  # Create the application GUI
    app.post_to_status_console("Program Start", "info")
    app.mainloop()
