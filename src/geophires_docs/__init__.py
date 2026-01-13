from __future__ import annotations

from pathlib import Path

_PROJECT_ROOT: Path = Path(__file__).parent.parent.parent
_FPC5_INPUT_FILE_PATH: Path = _PROJECT_ROOT / 'tests/examples/Fervo_Project_Cape-5.txt'
_FPC5_RESULT_FILE_PATH: Path = _PROJECT_ROOT / 'tests/examples/Fervo_Project_Cape-5.out'
