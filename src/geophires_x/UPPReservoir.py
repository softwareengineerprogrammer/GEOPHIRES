from __future__ import annotations

import sys
import numpy as np
from scipy.interpolate import interp1d

from .Parameter import strParameter, listParameter
from .Units import Units
import geophires_x.Model as Model
from .Reservoir import Reservoir


class UPPReservoir(Reservoir):
    """
    This class models the User Provided Profile Reservoir.
    """

    def __init__(self, model: Model):
        """
        The __init__ function is called automatically when a class is instantiated.
        It initializes the attributes of an object, and sets default values for certain arguments that can be overridden
        by user input.
        :param model: The container class of the application, giving access to everything else, including the logger
        :type model: :class:`~geophires_x.Model.Model`
        :return: None
        """
        model.logger.info("Init " + str(__class__) + ": " + sys._getframe().f_code.co_name)
        super().__init__(model)  # initialize the parent parameters and variables
        sclass = str(__class__).replace("<class \'", "")
        self.MyClass = sclass.replace("\'>", "")

        # Set up all the Parameters that will be predefined by this class using the different types of parameter classes.
        # Setting up includes giving it a name, a default value, The Unit Type (length, volume, temperature, etc.) and
        # Unit Name of that value, sets it as required (or not), sets allowable range, the error message if that range
        # is exceeded, the ToolTip Text, and the name of teh class that created it.
        # This includes setting up temporary variables that will be available to all the class but noy read in by user,
        # or used for Output
        # This also includes all Parameters that are calculated and then published using the Printouts function.
        # If you choose to subclass this master class, you can do so before or after you create your own parameters.
        # If you do, you can also choose to call this method from you class, which will effectively add and set all
        # these parameters to your class.
        # specific to this class:

        self.filenamereservoiroutput = self.ParameterDict[self.filenamereservoiroutput.Name] = strParameter(
            "Reservoir Output File Name",
            value='ReservoirOutput.txt',
            UnitType=Units.NONE,
            ErrMessage="assume default reservoir output file name (ReservoirOutput.txt)",
            ToolTipText="File name of reservoir output in case reservoir model 5 is selected",
        )

        self.reservoir_output_data = self.ParameterDict[self.reservoir_output_data.Name] = listParameter(
            "Reservoir Output Profile",
            DefaultValue=[],
            UnitType=Units.NONE,
            ToolTipText="Temperature profile data as a comma-separated list of values in Celsius. "
            "Values will be interpolated to match the simulation time steps. "
            "Example: 200,195,190,185 for a 4-point temperature decline profile.",
        )

        model.logger.info("Complete " + str(__class__) + ": " + sys._getframe().f_code.co_name)

    def __str__(self):
        return "UPPReservoir"

    def read_parameters(self, model: Model) -> None:
        model.logger.info("Init " + str(__class__) + ": " + sys._getframe().f_code.co_name)
        super().read_parameters(model)  # read the parameters for the parent.

        # Validate mutual exclusivity: user should provide either file or inline data, not both
        if self.reservoir_output_data.Provided and self.filenamereservoiroutput.Provided:
            # If both are provided, prefer inline data and log a warning
            msg = (
                "Both 'Reservoir Output Profile' and 'Reservoir Output File Name' were provided. "
                "Using 'Reservoir Output Profile' data."
            )
            print(f"Warning: {msg}")
            model.logger.warning(msg)

        model.logger.info("Complete " + str(__class__) + ": " + sys._getframe().f_code.co_name)

    def Calculate(self, model: Model):
        """
        The Calculate function calculates the values of the parameters that are calculated from other parameters.
        This includes the parameters that are calculated and then published using the Printouts function.
        :param model: The container class of the application, giving access to everything else, including the logger
        :type model: :class:`~geophires_x.Model.Model`
        :return: None
        """
        model.logger.info("Init " + str(__class__) + ": " + sys._getframe().f_code.co_name)
        super().Calculate(model)  # run calculations for the parent.

        model.reserv.Tresoutput.value[0] = model.reserv.Trock.value

        # Use the actual size of the Tresoutput array (set by parent Calculate)
        num_timesteps = len(model.reserv.Tresoutput.value)

        reservoir_temperatures: list[float] = self._get_reservoir_output_temperatures(model, num_timesteps)

        if len(reservoir_temperatures) != num_timesteps:
            # Shouldn't happen, but we'll log a warning if it does.
            model.logger.warning(
                f'Unexpected number of reservoir temperatures: '
                f'({len(reservoir_temperatures)}) found (expected {num_timesteps}).'
            )

        for i in range(num_timesteps):
            model.reserv.Tresoutput.value[i] = reservoir_temperatures[i]

        model.logger.info("Complete " + str(__class__) + ": " + sys._getframe().f_code.co_name)

    def _get_reservoir_output_temperatures(self, model: Model, num_timesteps: int):
        if self.reservoir_output_data.Provided and len(self.reservoir_output_data.value) > 0:
            reservoir_output_data = self._get_reservoir_output_data_from_profile_parameter(model)
        else:
            reservoir_output_data = self._get_reservoir_output_data_from_text_file(model, num_timesteps)

        # Create time points for the input data (evenly spaced over the plant lifetime)
        input_time_points = np.linspace(0, model.surfaceplant.plant_lifetime.value, len(reservoir_output_data))

        # Create target time points for the simulation
        target_time_points = np.linspace(0, model.surfaceplant.plant_lifetime.value, num_timesteps)

        # Interpolate temperature values to match simulation time steps
        interpolator = interp1d(input_time_points, reservoir_output_data, kind='linear', fill_value='extrapolate')
        interpolated_temps = interpolator(target_time_points)

        ret = [float(it) for it in interpolated_temps]

        if len(ret) != len(reservoir_output_data):
            model.logger.info(f'Reservoir Output Profile interpolation result: {ret}')

        return ret

    def _get_reservoir_output_data_from_profile_parameter(self, model: Model) -> list[float]:
        """
        Load reservoir temperature profile from inline data and interpolate to match time steps.
        """
        temp_data = self.reservoir_output_data.value

        if len(temp_data) < 2:
            msg = (
                "Error: 'Reservoir Output Profile' must contain at least 2 temperature values "
                f"for interpolation. Got {len(temp_data)} value(s)."
            )
            model.logger.critical(msg)
            raise RuntimeError(msg)

        return [float(it) for it in temp_data]

    # noinspection PyMethodMayBeStatic
    def _get_reservoir_output_data_from_text_file(self, model: Model, num_timesteps: int) -> list[float]:
        """
        Load reservoir temperature profile from file (original behavior).
        """
        try:
            with open(model.reserv.filenamereservoiroutput.value, encoding='UTF-8') as f:
                contentprodtemp = f.readlines()
        except Exception:
            msg = (
                'Error: GEOPHIRES could not read reservoir output file ('
                + model.reserv.filenamereservoiroutput.value
                + ') and will abort simulation.'
            )
            model.logger.critical(msg)
            raise RuntimeError(msg)

        num_lines = len(contentprodtemp)
        if num_lines != num_timesteps:
            msg = (
                f'Reservoir output file ({model.reserv.filenamereservoiroutput.value}; {num_lines} lines) does not have '
                f'required {num_timesteps} lines. '
                f'Profile data will be interpolated to match simulation time steps.'
            )
            model.logger.warning(msg)

        ret: list[float] = []
        for i in range(0, num_lines - 1):
            entry = float(contentprodtemp[i].split(',')[1].strip('\n'))
            ret.append(entry)

        return ret
