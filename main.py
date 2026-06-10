# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ultimation LLC and Robert C Suffern
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

__author__ = 'RCS'

import logging
import logging.handlers
import os
import traceback
from pathlib import Path

from Screen_Manager import PlexImportUtility


def _configure_logging():
    log_dir = Path(os.getenv("LOCALAPPDATA", "")) / "iTunesToPlex" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "app.log"

    fmt = logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s",
                             datefmt="%Y-%m-%d %H:%M:%S")

    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(fmt)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(file_handler)
    root.addHandler(stream_handler)

    return logging.getLogger(__name__)


if __name__ == '__main__':
    logger = _configure_logging()
    logger.info("Application starting")

    app = PlexImportUtility()

    def _tk_exception_handler(exc, val, tb):
        logger.error("Unhandled Tk exception: %s", val, exc_info=(exc, val, tb))
        app.post_to_status_console(
            f"Unexpected error: {val}  (see log for traceback)", "error")

    app.report_callback_exception = _tk_exception_handler
    app.post_to_status_console("Program Start", "info")
    app.mainloop()
    logger.info("Application exited")
