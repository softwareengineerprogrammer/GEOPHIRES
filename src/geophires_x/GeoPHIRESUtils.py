from __future__ import annotations

import logging
import sys
from enum import Enum
from os.path import exists
import dataclasses
import json
import numbers
from functools import lru_cache
from typing import Optional, Any

import scipy
from pint.facets.plain import PlainQuantity
from scipy.interpolate import interp1d
import numpy as np

import CoolProp.CoolProp as CP

from geophires_x.Parameter import ParameterEntry, Parameter
from geophires_x.Units import get_unit_registry, convertible_unit

_logger = logging.getLogger('root')  # TODO use __name__ instead of root

_T = np.array(
    [
        0.01,
        10.0,
        20.0,
        25.0,
        30.0,
        40.0,
        50.0,
        60.0,
        70.0,
        80.0,
        90.0,
        100.0,
        110.0,
        120.0,
        140.0,
        160.0,
        180.0,
        200.0,
        220.0,
        240.0,
        260.0,
        280.0,
        300.0,
        320.0,
        340.0,
        360.0,
        373.946,
        600.0,
    ]
)

# TODO needs citation
_UtilEff = np.array(
    [
        0.0,
        0.0,
        0.0,
        0.0,
        0.0057,
        0.0337,
        0.0617,
        0.0897,
        0.1177,
        0.13,
        0.16,
        0.19,
        0.22,
        0.26,
        0.29,
        0.32,
        0.35,
        0.38,
        0.40,
        0.4,
        0.4,
        0.4,
        0.4,
        0.4,
        0.4,
        0.4,
        0.4,
        0.5, # Extrapolate from fig 2 in https://geothermal-energy-journal.springeropen.com/articles/10.1186/s40517-019-0119-6
    ]
)

_interp_util_eff_func = interp1d(_T, _UtilEff)

_ureg = get_unit_registry()


def InsertImagesIntoHTML(html_path: str, short_names: set, full_names: set) -> None:
    # Write a reference to the image(s) into the HTML file by inserting before the "</body>" tag
    # build the string to be inserted first
    insert_string = ''
    for _ in range(len(full_names)):
        full_name = full_names.pop()
        name_to_use = full_name.name.replace('_', ' ').replace('.png', '')
        insert_string = insert_string + f'<img src="{full_name.name}" alt="{name_to_use}">\n<br>'

    match_string = '</body>'
    with open(html_path, 'r+', encoding='UTF-8') as html_file:
        contents = html_file.readlines()
        if match_string in contents[-1]:  # Handle last line to prevent IndexError
            pass
        else:
            for index, line in enumerate(contents):
                if match_string in line and insert_string not in contents[index + 1]:
                    contents.insert(index, insert_string)
                    break
        html_file.seek(0)
        html_file.writelines(contents)


def UpgradeSymbologyOfUnits(unit: str) -> str:
    """
    UpgradeSymbologyOfUnits is a function that takes a string that represents a unit and replaces the **2 and **3
    with the appropriate unicode characters for superscript 2 and 3, and replaces "deg" with the unicode character
    for degrees.
    :param unit: a string that represents a unit
    :return: a string that represents a unit with the appropriate unicode characters for superscript 2 and 3, and
    replaces "deg" with the unicode character for degrees.
    """

    return unit.replace('**2', '\u00b2').replace('**3', '\u00b3').replace('deg', '\u00b0')


def render_default(p: float, unit: str = '', fmt: str = '') -> str:
    """
    RenderDefault - render a float as a string with 2 decimal place by default, or whatever format the user specifies,
     or in scientific notation if it is greater than 10,000
     with the unit appended to it if it is not an empty string (the default)
    :param p: the float to render
    :type p: float
    :param unit: the unit to append to the string
    :type unit: str
    :param fmt: the format to use for the string representation of the float
    :type fmt: str
    :return: the string representation of the float
    """
    if not is_float(p):
        raise ValueError(f'Parameter ({p}) must be a float or convertible to float.')

    unit = UpgradeSymbologyOfUnits(unit)
    # if the number is greater than 10,000, render it in scientific notation
    if p > 10_000:
        return render_scientific(p, unit)
    # otherwise, render it with 2 decimal places
    else:
        if not fmt:
            return f'{p:10.2f} {unit}'.strip()
        else:
            if ':' in fmt:
                fmt = fmt.split(':')[1]
            fmt = '{0:' + fmt + '}{1:s}'
            return fmt.format(p, unit.strip())


def render_scientific(p: float, unit: str = '', fmt: str = '') -> str:
    """
    RenderScientific - render a float as a string in scientific notation with 2 decimal places by default, or whatever
    format the user specifies, and the unit appended to it if it is not an empty string (the default)
    :param p: the float to render
    :type p: float
    :param unit: the unit to append to the string
    :type unit: str
    :param fmt: the format to use for the string representation of the float
    :type fmt: str
    :return: the string representation of the float
    :rtype: str
    """

    if not is_float(p):
        raise ValueError(f'Parameter ({p}) must be a float or convertible to float.')

    unit = UpgradeSymbologyOfUnits(unit)
    if not fmt:
        return f'{p:10.2e} {unit}'.strip()
    else:
        pass


def render_Parameter_default(p: Parameter, fmt: str = '') -> str:
    """
    RenderDefault - render a float parameter in scientific notation as a string with 2 decimal places,
     or whatever format the user specifies with the unit appended to it if it is not an empty string (the default)
    function
    :param p: the parameter to render
    :type p: Parameter
    :param fmt: the format to use for the string representation of the float
    :type fmt: str
    :return: the string representation of the float
    """
    if not is_float(p.value):
        raise ValueError(f'Parameter ({p.value}) must be a float or convertible to float.')

    return render_default(p.value, p.CurrentUnits.value)


def render_parameter_scientific(p: Parameter, fmt: str = '') -> str:
    """
    RenderScientific - render a float as a string in scientific notation with 2 decimal places
    and the unit appended to it if it is not an empty string (the default) by calling the render_scientific base function
    :param p: the parameter to render
    :type p: float
    :param fmt: the format to use for the string representation of the float
    :type fmt: str
    :return: the string representation of the float
    """

    if not is_float(p.value):
        raise ValueError(f'Parameter ({p.value}) must be a float or convertible to float.')

    return render_scientific(p.value, p.CurrentUnits.value)


def quantity(value: float, unit: str) -> PlainQuantity:
    """
    :rtype: pint.registry.Quantity - note type annotation uses PlainQuantity due to issues with python 3.8 failing
        to import the Quantity TypeAlias
    """
    return _ureg.Quantity(value, convertible_unit(unit))


@lru_cache
def density_water_kg_per_m3(Twater_degC: float, pressure: Optional[PlainQuantity] = None) -> float:
    """
    Calculate the density of water as a function of temperature.

    Args:
        Twater_degC: The temperature of water in degrees C.
        pressure: Pressure - should be provided as a Pint quantity that knows its units
    Returns:
        The density of water in kg/m³.
    Raises:
        ValueError: If Twater_degC is not a float or convertible to float.
    """
    if not is_float(Twater_degC):
        raise ValueError(f'Twater_degC ({Twater_degC}) must be a float or convertible to float.')

    try:
        if pressure is not None:
            return CP.PropsSI('D', 'T', celsius_to_kelvin(Twater_degC), 'P', pressure.to('Pa').magnitude, 'Water')
        else:
            _logger.warning(f'density_water: No pressure provided, using vapor quality=0 instead')
            return CP.PropsSI('D', 'T', celsius_to_kelvin(Twater_degC), 'Q', 0, 'Water')

    except (NotImplementedError, ValueError) as e:
        raise ValueError(f'Input temperature & pressure ({Twater_degC}, {pressure}) '
                         f'are out of range or otherwise could not be used to calculate water density.') from e


def celsius_to_kelvin(celsius: float) -> float:
    """
    Convert temperature from Celsius to Kelvin.

    Args:
        celsius: Temperature in degrees Celsius.
    Returns:
        Temperature in Kelvin.
    Raises:
        ValueError: If celsius is not a float or convertible to float.
    """
    if not isinstance(celsius, (int, float)):
        raise ValueError(f"Invalid input for celsius ({celsius}). celsius must be a number.")

    CELSIUS_TO_KELVIN_CONSTANT = 273.15
    return celsius + CELSIUS_TO_KELVIN_CONSTANT


@lru_cache
def viscosity_water_Pa_sec(
    Twater_degC: float,
    pressure: Optional[PlainQuantity] = None) -> float:
    """
    Calculate the dynamic viscosity of water as a function of temperature and pressure.

    Args:
        Twater_degC: the temperature of water in degrees C
        pressure: Pressure - should be provided
    Returns:
        Viscosity of water in Pa·s (Ns/m2)
    Raises:
        ValueError: If Twater_degC is not a float or convertible to float.
    """

    try:
        if pressure is not None:
            return CP.PropsSI('V', 'T', celsius_to_kelvin(Twater_degC), 'P', pressure.to('Pa').magnitude, 'Water')
        else:
            _logger.warning(f'viscosity_water: No pressure provided, using vapor quality=0 instead')
            return CP.PropsSI('V', 'T', celsius_to_kelvin(Twater_degC), 'Q', 0, 'Water')

    except (NotImplementedError, ValueError) as e:
        raise ValueError(f'Input temperature & pressure ({Twater_degC}, {pressure}) '
                         f'are out of range or otherwise could not be used to calculate water viscosity.') from e


@lru_cache
def heat_capacity_water_J_per_kg_per_K(
    Twater_degC: float,
    pressure: Optional[PlainQuantity] = None,
) -> float:
    """
    Calculate the isobaric specific heat capacity (c_p) of water as a function of temperature.

    Args:
        Twater_degC: The temperature of water in degrees C.
        pressure: Pressure - should be provided
    Returns:
        The isobaric specific heat capacity of water as a function of temperature in J/(kg·K).
    Raises:
        ValueError: If Twater_degC is not a float or convertible to float.
    """
    max_allowed_temp_degC = 600
    if not isinstance(Twater_degC, numbers.Real) or Twater_degC < 0 or Twater_degC > max_allowed_temp_degC:
        raise ValueError(
            f'Invalid input for Twater_degC. '
            f'Twater_degC must be a non-negative number and must be within the range of 0 to {max_allowed_temp_degC} '
            f'degrees Celsius. The input value was: {Twater_degC}'
        )

    try:
        if pressure is not None:
            return CP.PropsSI('C', 'T', celsius_to_kelvin(Twater_degC), 'P', pressure.to('Pa').magnitude, 'Water')
        else:
            _logger.warning(f'heat_capacity_water: No pressure provided, using vapor quality=0 instead')
            return CP.PropsSI('C', 'T', celsius_to_kelvin(Twater_degC), 'Q', 0, 'Water')

    except (NotImplementedError, ValueError) as e:
        raise ValueError(f'Input temperature & pressure ({Twater_degC}, {pressure}) '
                         f'are out of range or otherwise could not be used to calculate heat capacity of water.') from e


@lru_cache
def RecoverableHeat(Twater_degC: float) -> float:
    """
    the RecoverableHeat function is used to calculate the recoverable heat fraction as a function of temperature

    Args:
        Twater_degC: the temperature of water in degrees C
    Returns:
        the recoverable heat fraction as a function of temperature
    Raises:
        ValueError: If Twater is not a float or convertible to float.
        ValueError: If DefaultRecoverableHeat is not a float or convertible to float.
    """
    LOW_TEMP_THRESHOLD = 90.0
    HIGH_TEMP_THRESHOLD = 150.0
    LOW_TEMP_RECOVERABLE_HEAT = 0.43
    HIGH_TEMP_RECOVERABLE_HEAT = 0.66

    if not isinstance(Twater_degC, (int, float)):
        raise ValueError(f'Twater_degC {Twater_degC} must be a number')

    if Twater_degC <= LOW_TEMP_THRESHOLD:
        recoverable_heat = LOW_TEMP_RECOVERABLE_HEAT
    elif Twater_degC >= HIGH_TEMP_THRESHOLD:
        recoverable_heat = HIGH_TEMP_RECOVERABLE_HEAT
    else:
        recoverable_heat = 0.0038 * Twater_degC + 0.085

    return recoverable_heat


@lru_cache
def vapor_pressure_water_kPa(temperature_degC: float) -> float:
    """
    Calculate the vapor pressure of water as a function of temperature.

    Args:
        temperature_degC: the temperature of water in degrees C
    Returns:
        The vapor pressure of water as a function of temperature in kPa
    Raises:
        ValueError: If temperature_degC is not a float or convertible to float.
        ValueError: If temperature_degC is below 0.
    """

    if not isinstance(temperature_degC, (int, float)):
        raise ValueError(f'Input temperature ({temperature_degC}) must be a number')
    if temperature_degC < 0:
        raise ValueError(f'Input temperature ({temperature_degC}C) must be greater than or equal to 0')

    try:
        return (quantity(CP.PropsSI('P', 'T', celsius_to_kelvin(temperature_degC), 'Q', 0, 'Water'), 'Pa')
                .to('kPa').magnitude)

    except (NotImplementedError, ValueError) as e:
        raise ValueError(f'Input temperature ({temperature_degC}C) is out of range or otherwise not implemented') from e


@lru_cache
def entropy_water_kJ_per_kg_per_K(temperature_degC: float, pressure: Optional[PlainQuantity] = None) -> float:
    """
    Calculate the entropy of water as a function of temperature

    Args:
        temperature_degC: the temperature of water in degrees C
        pressure: Pressure - should be provided as a Pint quantity that knows its units
    Returns:
        the entropy of water as a function of temperature in kJ/(kg·K)
    Raises:
        TypeError: If temperature is not a float or convertible to float.
        ValueError: If temperature and pressure combination are not within lookup range
    """

    try:
        temperature_degC = float(temperature_degC)
    except ValueError:
        raise TypeError(f'Input temperature ({temperature_degC}) must be a float')

    try:
        if pressure is not None:
            return CP.PropsSI('S', 'T', celsius_to_kelvin(temperature_degC),
                              'P', pressure.to('Pa').magnitude, 'Water') * 1e-3
        else:
            return CP.PropsSI('S', 'T', celsius_to_kelvin(temperature_degC), 'Q', 0, 'Water') * 1e-3
    except (NotImplementedError, ValueError) as e:
        raise ValueError(f'Input temperature {temperature_degC} is out of range or otherwise not implemented') from e


@lru_cache
def enthalpy_water_kJ_per_kg(temperature_degC: float, pressure: Optional[PlainQuantity] = None) -> float:
    """
    Calculate the enthalpy of water as a function of temperature

    Args:
        temperature_degC: the temperature of water in degrees C (float)
        pressure: Pressure - should be provided as a Pint quantity that knows its units
    Returns:
        the enthalpy of water as a function of temperature in kJ/kg
    Raises:
        TypeError: If temperature is not a float or convertible to float.
        ValueError: If temperature and pressure combination are not within lookup range
    """

    try:
        temperature_degC = float(temperature_degC)
    except ValueError:
        raise TypeError(f'Input temperature ({temperature_degC}) must be a float')

    try:
        if pressure is not None:
            return CP.PropsSI('H', 'T', celsius_to_kelvin(temperature_degC),
                              'P', pressure.to('Pa').magnitude, 'Water') * 1e-3
        else:
            return CP.PropsSI('H', 'T', celsius_to_kelvin(temperature_degC), 'Q', 0, 'Water') * 1e-3

    except (NotImplementedError, ValueError) as e:
        raise ValueError(f'Input temperature {temperature_degC} is out of range or otherwise not implemented') from e


@lru_cache
def UtilEff_func(temperature_degC: float) -> float:
    """
    the UtilEff_func function is used to calculate the utilization efficiency of the system as a function of temperature
    Args:
        temperature_degC: the temperature of water in degrees C
    Returns:
         the utilization efficiency of the system as a function of temperature
    Raises:
        ValueError: If x is not a float or convertible to float.
        ValueError: If x is not within the range of 0 to 373.946 degrees C.
    """

    if not isinstance(temperature_degC, (int, float)):
        raise ValueError(f'Input temperature ({temperature_degC}) must be a number')

    if temperature_degC < _T[0] or temperature_degC > _T[-1]:
        raise ValueError(f'Temperature ({temperature_degC}) must be within the range of {_T[0]} to {_T[-1]} degrees C.')

    util_eff = _interp_util_eff_func(temperature_degC)
    return util_eff


def read_input_file(return_dict_1, logger=None, input_file_name=None):
    """
    Read input file and return a dictionary of parameters
    :param return_dict_1: dictionary of parameters
    :param logger: logger object
    :return: dictionary of parameters
    :rtype: dict

    FIXME modifies dict instead of returning it - it should do what the doc says it does and return a dict instead,
      relying on mutation of parameters is Bad
    """

    if logger is None:
        logger = logging.getLogger(__name__)

    logger.info(f'Init {__name__}')

    # Specify path of input file - it will always be the first command line argument.
    # If it doesn't exist, simply run the default model without any inputs

    # read input data (except input from optional filenames)
    if input_file_name is None:
        logger.warning('Input file name not provided, checking sys.argv')
        if len(sys.argv) > 1:
            input_file_name = sys.argv[1]
            logger.warning(f'Using input file from sys.argv: {input_file_name}')

    if input_file_name is not None:
        content = []
        if exists(input_file_name):
            logger.info(f'Found filename: {input_file_name}. Proceeding with run using input parameters from that file')
            with open(input_file_name, encoding='UTF-8') as f:
                # store all input in one long string that will be passed to all objects
                # so they can parse out their specific parameters (and ignore the rest)
                content = f.readlines()
        else:
            raise FileNotFoundError(f'Unable to read input file: File {input_file_name} not found')

        # successful read of data into list.  Now make a dictionary with all the parameter entries.
        # Index will be the unique name of the parameter.
        # The value will be a "ParameterEntry" structure, with name, value (optionally with units), optional comment
        for raw_line in content:
            line = raw_line.strip()
            if any([line.startswith(x) for x in ['#', '--', '*']]):
                # skip any line that starts with "#" - # will be the comment parameter
                continue

            # now deal with the comma delimited parameters
            # split on a comma - that should give us major divisions,
            # Could be:
            # 1) Desc and Val (2 elements),
            # 2) Desc and Val with Unit (2 elements, Unit split from Val by space),
            # 3) Desc, Val, and comment (3 elements),
            # 4) Desc, Val with Unit, Comment (3 elements, Unit split from Val by space)
            # If there are more than 3 commas, we are going to assume it is parseable,
            # and that the commas are in the comment
            elements = line.split(',')

            if len(elements) < 2:
                # not enough commas, so must not be data to parse
                continue

                # we have good data, so make initial assumptions
            description = elements[0].strip()
            s_val = elements[1].strip()
            comment = ""  # cases 1 & 2 - no comment
            if len(elements) == 3:  # cases 3 & 4
                comment = elements[2].strip()

            if len(elements) > 3:
                # too many commas, so assume they are in comments
                for i in range(2, len(elements), 1):
                    comment = comment + elements[i]

            # done with parsing, now create the object and add to the dictionary
            p_entry = ParameterEntry(description, s_val, comment, line)
            return_dict_1[description] = p_entry  # make the dictionary element

    else:
        logger.warning(
            'No input parameter file specified on the command line. '
            'Proceeding with default parameter run...'
        )

    logger.info(f'Complete {__name__}: {sys._getframe().f_code.co_name}')


class _EnhancedJSONEncoder(json.JSONEncoder):
    """
    Enhanced JSON encoder that can handle dataclasses
    :param json.JSONEncoder: JSON encoder
    :return: JSON encoder
    :rtype: json.JSONEncoder
    """

    def default(self, o):
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)

        if issubclass(o, Enum):
            def get_entry(member) -> dict[str, Any]:
                d = {
                    'name': member.name,
                    'value': member.value
                }

                if hasattr(member, 'int_value'):
                    d['int_value'] = member.int_value

                return d

            ret = [get_entry(member) for member in o]
            return ret

        return super().default(o)


def json_dumpse(obj) -> str:
    return json.dumps(obj, cls=_EnhancedJSONEncoder)


def static_pressure_MPa(rho_kg_per_m3: float, depth_m: float) -> float:
    """
    Calculate static pressure in a reservoir (i.e. lithostatic pressure or hydrostatic pressure).

    Args:
        rho_kg_per_m3 (float): Density of the fluid in kg/m^3.
        depth_m (float): Depth of the reservoir in meters.
    Returns:
        float: Static pressure in megapascals (MPa).
    """

    g = scipy.constants.g  # Acceleration due to gravity (m/s^2)

    # Calculate lithostatic pressure
    pressure_Pa = rho_kg_per_m3 * g * depth_m

    pressure_mpa = quantity(pressure_Pa, 'Pa').to('MPa').magnitude

    return pressure_mpa


def is_int(o: Any) -> bool:
    try:
        float_n = float(o)
        int_n = int(float_n)
    except ValueError:
        return False
    else:
        return float_n == int_n


def is_float(o: Any) -> bool:
    try:
        float(o)
    except ValueError:
        return False
    except TypeError:
        return False
    else:
        return True


def sig_figs(val: float | list | tuple, num_sig_figs: int) -> float:
    if val is None:
        return None

    if isinstance(val, list) or isinstance(val, tuple):
        return [sig_figs(v, num_sig_figs) for v in val]

    try:
        return float('%s' % float(f'%.{num_sig_figs}g' % val))  # pylint: disable=consider-using-f-string
    except TypeError:
        # TODO warn
        return val
