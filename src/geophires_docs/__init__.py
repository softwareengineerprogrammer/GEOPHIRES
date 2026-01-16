from __future__ import annotations

import os
from pathlib import Path


def _get_file_path(file_name) -> Path:
    return Path(os.path.join(os.path.abspath(os.path.dirname(__file__)), file_name))


def _get_project_root() -> Path:
    return _get_file_path('../..')


def _get_fpc5_input_file_path(project_root: Path | None = None) -> Path:
    if project_root is None:
        project_root = _get_project_root()
    return project_root / 'tests/examples/Fervo_Project_Cape-5.txt'


def _get_fpc5_result_file_path(project_root: Path | None = None) -> Path:
    if project_root is None:
        project_root = _get_project_root()
    return project_root / 'tests/examples/Fervo_Project_Cape-5.out'


_PROJECT_ROOT: Path = _get_project_root()
_FPC5_INPUT_FILE_PATH: Path = _get_fpc5_input_file_path()
_FPC5_RESULT_FILE_PATH: Path = _get_fpc5_result_file_path()
