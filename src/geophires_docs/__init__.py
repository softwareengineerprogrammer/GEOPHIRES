from __future__ import annotations

import os
from pathlib import Path


def _get_file_path(file_name) -> Path:
    return Path(os.path.join(os.path.abspath(os.path.dirname(__file__)), file_name))


_PROJECT_ROOT: Path = _get_file_path('../..')
_FPC5_INPUT_FILE_PATH: Path = _PROJECT_ROOT / 'tests/examples/Fervo_Project_Cape-5.txt'
_FPC5_RESULT_FILE_PATH: Path = _PROJECT_ROOT / 'tests/examples/Fervo_Project_Cape-5.out'
