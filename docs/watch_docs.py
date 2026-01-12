#!python
# Automatically rebuilds docs locally when changes are detected.
# Usage, from the project root:
# ./docs/watch_docs.py

import os
import subprocess
import time
from pathlib import Path
from typing import Any


def _get_logger():
    # sh = logging.StreamHandler(sys.stdout)
    # sh.setLevel(logging.INFO)
    # sh.setFormatter(logging.Formatter(fmt='[%(asctime)s][%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
    #
    # ret = logging.getLogger(__name__)
    # ret.addHandler(sh)
    # return ret

    # noinspection PyMethodMayBeStatic
    class _PrintLogger:
        def info(self, msg):
            print(f'[INFO] {msg}')

        def error(self, msg):
            print(f'[ERROR] {msg}')

    return _PrintLogger()


_log = _get_logger()


def get_file_states(directory) -> dict[str, Any]:
    """
    Returns a dictionary of file paths and their modification times.
    """
    states = {}
    for root, _, files in os.walk(directory):
        for filename in files:
            # Ignore hidden files, temporary editor files, and this script itself
            # fmt:off
            if (filename.startswith('.') or
                filename.endswith('~') or filename == os.path.basename(__file__)):  # noqa: PTH119
                # fmt:on
                continue

            filepath = os.path.join(root, filename)

            # Avoid watching build directories if they are generated inside docs/
            if '_build' in filepath or 'build' in filepath:
                continue

            try:
                states[filepath] = os.path.getmtime(filepath)  # noqa: PTH204
            except OSError:
                pass
    return states


def main():
    # Determine paths relative to this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root: str = os.path.dirname(script_dir)

    def _say(msg) -> None:
        try:
            subprocess.run(['say', msg], cwd=project_root, check=False)  # noqa: S603,S607
        except subprocess.CalledProcessError:
            pass

    # Watch the directory where the script is located (docs/)
    watch_dir = script_dir

    command = ['tox', '-e', 'docs']
    poll_interval = 2  # Seconds

    _log.info(f"Watching '{watch_dir}' for changes...")
    _log.info(f"Project root determined as: '{project_root}'")
    _log.info(f"Command to run: {' '.join(command)}")
    _log.info('Press Ctrl+C to stop.')

    def _get_file_states() -> dict:
        return {**get_file_states(watch_dir), **get_file_states(Path(project_root) / 'tests' / 'examples')}

    # Initial state
    last_states = _get_file_states()

    try:
        while True:
            time.sleep(poll_interval)
            current_states = _get_file_states()

            if current_states != last_states:
                _log.info('\n[Change Detected] Running docs build...')
                time.sleep(1)

                try:
                    # Run tox from the project root so it finds tox.ini
                    subprocess.run(command, cwd=project_root, check=False)  # noqa: S603
                except FileNotFoundError:
                    _log.error("Error: 'tox' command not found. Please ensure tox is installed.")
                except Exception as e:
                    _log.error(f'An error occurred: {e}')
                    _say('error rebuilding docs')

                _log.info(f"\nDocs rebuild complete at {time.strftime('%Y-%m-%d %H:%M:%S')}.")
                _say('docs rebuilt')
                _log.info(f"\nWaiting for further changes in '{watch_dir}'...")

                # Update state to the current state
                last_states = _get_file_states()

    except KeyboardInterrupt:
        _log.info('\nWatcher stopped.')


if __name__ == '__main__':
    main()
