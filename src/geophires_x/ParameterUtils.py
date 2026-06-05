from __future__ import annotations

import copy
import logging

from geophires_x.GeoPHIRESUtils import is_float, is_int
from geophires_x.Parameter import SCHEDULE_DSL_MULTIPLIER_SYMBOL


_log = logging.getLogger(__name__)


def expand_schedule_dsl(
    schedule_strings: list[str | float], total_years: int, allow_schedule_length_to_exceed_total_years: bool = False
) -> list[float]:
    """
    Parse a duration-based scheduling DSL and expand it into a fixed-length time-series array.

    Syntax: `[Value] * [Years], [Value] * [Years], ..., [Terminal Value]`

    The terminal (last) value is repeated to fill `total_years`.  A bare scalar
    (e.g. `['2.5']`) is treated as a terminal value and broadcast across all years.

    Examples::

        expand_schedule_dsl(['1.0 * 3', '0.1'], total_years=6)
        # => [1.0, 1.0, 1.0, 0.1, 0.1, 0.1]

        expand_schedule_dsl(['2.5'], total_years=4)
        # => [2.5, 2.5, 2.5, 2.5]

    :param schedule_strings: list of DSL segment strings.  Each element is either
        `"<value> * <years>"` (a run-length segment) or `"<value>"` (a scalar,
        which becomes the terminal value when it is the last element, or a 1-year
        segment otherwise).
    :param total_years: The total number of years the expanded array must span
        (typically `construction_years + plant_lifetime`).
    :returns: A `list[float]` of length `total_years`.
    :raises ValueError: On malformed DSL strings or when explicit segments exceed
        `total_years`.
    """

    if total_years <= 0:
        return []

    if not schedule_strings:
        return [0.0] * total_years

    segments: list[tuple[float, int | None]] = []
    for raw in schedule_strings:
        raw = str(raw).strip()
        if SCHEDULE_DSL_MULTIPLIER_SYMBOL in raw:
            parts = raw.split(SCHEDULE_DSL_MULTIPLIER_SYMBOL)
            if len(parts) != 2:
                raise ValueError(f'Invalid schedule segment "{raw}": expected "<value> * <years>".')

            val_raw = parts[0].strip()
            if not is_float(val_raw):
                raise ValueError(f'Invalid schedule segment "{raw}": "{val_raw}" is not a float.')
            value = float(val_raw)
            if value < 0:
                raise ValueError(f'Invalid schedule segment "{raw}": {val_raw} is negative.')

            years_raw = parts[1].strip()
            if not is_int(years_raw):
                raise ValueError(f'Invalid schedule segment "{raw}": "{years_raw}" is not an int.')

            years = int(years_raw)
            if years < 0:
                raise ValueError(f'Invalid schedule segment "{raw}": year count must be non-negative.')
            segments.append((value, years))
        else:
            if not is_float(raw):
                raise ValueError(f'Invalid schedule segment "{raw}": "{raw}" is not a float.')

            value = float(raw)
            segments.append((value, None))

    result: list[float] = []
    terminal_value = 0.0

    for idx, (value, years) in enumerate(segments):
        is_last = idx == len(segments) - 1
        if years is not None:
            result.extend([value] * years)
            terminal_value = value
        else:
            if is_last:
                terminal_value = value
            else:
                result.append(value)
                terminal_value = value

    remaining = total_years - len(result)
    if remaining > 0:
        result.extend([terminal_value] * remaining)

    if len(result) > total_years:
        if not allow_schedule_length_to_exceed_total_years:
            raise ValueError(
                f'Invalid schedule: Schedule expands to {len(result)} years '
                f'which exceeds total_years={total_years}.'
            )
        else:
            pre_truncation_result = copy.copy(result)
            result = result[:total_years]
            _log.warning(
                f'Schedule expands to {len(pre_truncation_result)} years, which exceeds total_years={total_years}. '
                f'Schedule has been truncated to {total_years} years ({result}; from {pre_truncation_result}).'
            )

    return result
