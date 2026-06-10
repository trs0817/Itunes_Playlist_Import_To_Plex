# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ultimation LLC and Robert C Suffern
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import os
import sys


def resource_path(relative_path: str) -> str:
    """Return the absolute path to a bundled resource.

    Works both when running from source (returns a path relative to this
    file's directory) and when frozen by PyInstaller (uses sys._MEIPASS,
    the temp directory where the bundle is extracted at runtime).
    """
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative_path)
