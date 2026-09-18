from __future__ import annotations

import argparse
import os
import sys
import tempfile
import uuid
from pathlib import Path

from hip_ra import HipRaInputParameters
from hip_ra_x import HipRaXClient
from hip_ra_x import HipRaXResult

parser = argparse.ArgumentParser(description='HIP-RA-X CLI')
parser.add_argument('input-file', nargs=1, help='Input file path')
# parser.add_argument('output-file', nargs='?', help='Output file path')
parsed_args = {k: v for k, v in vars(parser.parse_args()).items() if v is not None}

stash_cwd = Path.cwd()
stash_sys_argv = sys.argv

if 'input-file' in parsed_args:
    input_file = Path(parsed_args['input-file'][0]).absolute()

if 'output-file' in parsed_args:
    sys.argv[2] = Path(parsed_args['output-file']).absolute()
else:
    if len(sys.argv) < 3:
        sys.argv.append('')

    sys.argv[2] = Path(stash_cwd, 'HDR.out').absolute()

rc = 1
try:
    with open(input_file, encoding='utf-8') as f:
        input_file_lines = f.readlines()

    input_file_lines.append('Print Output to Console, False')

    tmp_input_file_with_print_to_console_disabled = Path(tempfile.gettempdir(), f'hip-ra-params_{uuid.uuid1()}.txt')
    with open(tmp_input_file_with_print_to_console_disabled, 'w') as f:
        f.writelines(input_file_lines)

    input_params: HipRaInputParameters = HipRaInputParameters(
        Path(tmp_input_file_with_print_to_console_disabled).absolute()
    )
    result: HipRaXResult = HipRaXClient().get_hip_ra_x_result(input_params)

    with open(input_params.output_file_path, encoding='utf-8') as f:
        print('\n' + f.read())

    rc = 0
finally:
    # Undo internal global settings changes
    sys.argv = stash_sys_argv
    os.chdir(stash_cwd)

sys.exit(rc)
