import os
import sys
from pathlib import Path

from geophires_x_client.common import _get_logger
from hip_ra import HipRaInputParameters
from hip_ra import HipRaResult
from hip_ra_x import hip_ra_x
from hip_ra_x.hip_ra_x_result import HipRaXResult


class HipRaXClient:
    def __init__(self, enable_caching=True, logger_name='root'):
        self._logger = _get_logger(logger_name=logger_name)

    def get_hip_ra_result(self, input_params: HipRaInputParameters) -> HipRaResult:
        stash_cwd = Path.cwd()
        stash_sys_argv = sys.argv

        sys.argv = ['', input_params.as_file_path(), input_params.output_file_path]
        try:
            hip_ra_x.main(enable_hip_ra_logging_config=False)
        except Exception as e:
            raise RuntimeError(f'HIP-RA-X encountered an exception: {e!s}') from e
        except SystemExit:
            raise RuntimeError('HIP-RA-X exited without giving a reason') from None
        finally:
            # Undo HIP-RA internal global settings changes
            sys.argv = stash_sys_argv
            os.chdir(stash_cwd)

        self._logger.info(f'HIP-RA-X output file: {input_params.output_file_path}')

        return HipRaResult(input_params.output_file_path)

    def get_hip_ra_x_result(self, input_params: HipRaInputParameters) -> HipRaXResult:
        return HipRaXResult.from_hip_ra_result(self.get_hip_ra_result(input_params))
