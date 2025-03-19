import sys
import numpy as np
from .Parameter import floatParameter, strParameter
from .Units import *
import geophires_x.Model as Model
from geophires_x.Reservoir import Reservoir


class TOUGH2Reservoir(Reservoir):
    """
    This class models the TOUGH2 Reservoir.
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
        super().__init__(model)   # initialize the parent parameters and variables
        sclass = str(__class__).replace("<class \'", "")
        self.MyClass = sclass.replace("\'>", "")

        # Set up all the Parameters that will be predefined by this class using the different types of parameter classes.
        # Setting up includes giving it a name, a default value, The Unit Type (length, volume, temperature, etc) and
        # Unit Name of that value, sets it as required (or not), sets allowable range, the error message if that range
        # is exceeded, the ToolTip Text, and the name of teh class that created it.
        # This includes setting up temporary variables that will be available to all the class but noy read in by user,
        # or used for Output
        # This also includes all Parameters that are calculated and then published using the Printouts function.
        # specific to this stype of reservoir
        self.tough2_executable_path = self.ParameterDict[self.tough2_executable_path.Name] = strParameter(
            "TOUGH2 Executable Path",
            DefaultValue='xt2_eos1.exe',
            UnitType=Units.NONE,
        )
        self.tough2modelfilename = self.ParameterDict[self.tough2modelfilename.Name] = strParameter(
            "TOUGH2 Model/File Name",
            DefaultValue='Doublet',
            UnitType=Units.NONE,
            ErrMessage="assume default built-in TOUGH2 model (Doublet).",
            ToolTipText="File name of reservoir output in case reservoir model 5 is selected"
        )
        self.resthickness = self.ParameterDict[self.resthickness.Name] = floatParameter(
            "Reservoir Thickness",
            value=250.0,
            Min=5,
            Max=10000,
            UnitType=Units.LENGTH,
            PreferredUnits=LengthUnit.METERS,
            CurrentUnits=LengthUnit.METERS,
            ErrMessage="assume default reservoir thickness (250 m)",
            ToolTipText="Reservoir thickness for built-in TOUGH2 doublet reservoir model"
        )
        self.reswidth = self.ParameterDict[self.reswidth.Name] = floatParameter(
            "Reservoir Width",
            value=500.0,
            Min=10, Max=10000,
            UnitType=Units.LENGTH,
            PreferredUnits=LengthUnit.METERS,
            CurrentUnits=LengthUnit.METERS,
            ErrMessage="assume default reservoir width (500 m)",
            ToolTipText="Reservoir width for built-in TOUGH2 doublet reservoir model"
        )

        model.logger.info("Complete " + str(__class__) + ": " + sys._getframe().f_code.co_name)

    def __str__(self):
        return "TOUGH2Reservoir"

    def read_parameters(self, model:Model) -> None:
        """
        The read_parameters function reads in the parameters from a dictionary created by reading the user-provided file
         and updates the parameter values for this object.
        The function reads in all the parameters that relate to this object, including those that are inherited from
         other objects. It then updates any of these parameter values that have been changed by the user.
           It also handles any special cases.
        :param model: The container class of the application, giving access to everything else, including the logger
        :type model: :class:`~geophires_x.Model.Model`
        :return: None
        """
        model.logger.info("Init " + str(__class__) + ": " + sys._getframe().f_code.co_name)
        super().read_parameters(model)    # read the parameters for the parent.
        # if we call super, we don't need to deal with setting the parameters here, just deal with the special cases
        # for the variables in this class
        # because the call to the super.readparameters will set all the variables,
        # including the ones that are specific to this class

        # Deal with all the parameter values that the user has provided.  They should really only provide values that
        # they want to change from the default values, but they can provide a value that is already set because it is a
        # default value set in __init__. It will ignore those
        # This also deals with all the special cases that need to be taken care of after a value
        # has been read in and checked.
        # If you choose to subclass this master class, you can also choose to override this method (or not),
        # and if you do, do it before or after you call you own version of this method.  If you do, you can also
        # choose to call this method from you class, which can effectively modify all these superclass parameters
        # in your class.

        if len(model.InputParameters) > 0:
            # loop through all the parameters that the user wishes to set, looking for parameters that match this object
            for item in self.ParameterDict.items():
                ParameterToModify = item[1]
                key = ParameterToModify.Name.strip()
                if key in model.InputParameters:
                    ParameterReadIn = model.InputParameters[key]
                    # handle special cases
                    if ParameterToModify.Name == "TOUGH2 Model/File Name":
                        if self.tough2modelfilename.value.startswith('Doublet'):
                            self.usebuiltintough2model = True
                        else:
                            self.usebuiltintough2model = False

        model.logger.info("Complete " + str(__class__) + ": " + sys._getframe().f_code.co_name)

    def Calculate(self, model:Model):
        """
        The Calculate function calculates the values of all the parameters that are calculated by this object.
        It calls the Calculate function of the parent object to calculate the values of the parameters that are
        calculated by the parent object.
        It then calculates the values of the parameters that are calculated by this object.
        :param model: The container class of the application, giving access to everything else, including the logger
        :type model: :class:`~geophires_x.Model.Model`
        :return: None
        """
        model.logger.info("Init " + str(__class__) + ": " + sys._getframe().f_code.co_name)
        super().Calculate(model)    # run calculate for the parent.

        # GEOPHIRES assumes TOUGH2 executable and input file are in same directory as GEOPHIRESv3.py, however the path can be specified inside GEOPHIRES input file
        # create tough2 input file
        path_to_exe = str(self.tough2_executable_path.value)
        injection_cell_id = "A3Q23"
        production_cell_id = "A3Q28"
        if not os.path.exists(os.path.join(os.getcwd(), path_to_exe)):
            model.logger.critical('TOUGH2 executable file does not exist in current working directory. \
            GEOPHIRES will abort simulation.')
            print('TOUGH2 executable file does not exist in current working directory. \
            GEOPHIRES will abort simulation.')
            sys.exit()
        if model.reserv.tough2modelfilename.value == 'Doublet':
            infile = str('Doublet.dat')
            outfile = str('Doublet.out')
            initialtemp = model.reserv.Trock.value
            rockthermalcond = model.reserv.krock.value
            rockheatcap = model.reserv.cprock.value
            rockdensity = model.reserv.rhorock.value
            rockpor = model.reserv.porrock.value
            rockperm = model.reserv.permrock.value
            reservoirthickness = model.reserv.resthickness.value
            reservoirwidth = model.reserv.reswidth.value
            wellseperation = model.wellbores.wellsep.value
            DeltaXgrid = 10000/50
            DeltaYgrid = reservoirwidth/50
            DeltaZgrid = reservoirthickness
            flowrate = model.wellbores.prodwellflowrate.value
            print('Reservoir parameters passed to TOUGH from Reservoir.py \n')
            print(initialtemp, rockdensity, rockheatcap, rockperm, rockpor, rockthermalcond, reservoirthickness,
                  reservoirwidth, wellseperation, DeltaXgrid, DeltaYgrid, DeltaZgrid)

            # convert injection temperature to injection enthalpy
            arraytinj = np.array([1.8,    11.4,  23.4,  35.4,  47.4,  59.4,  71.3,  83.3,  95.2, 107.1, 118.9])
            arrayhinj = np.array([1.0E4, 5.0E4, 1.0E5, 1.5E5, 2.0E5, 2.5E5, 3.0E5, 3.5E5, 4.0E5, 4.5E5, 5.0E5])
            injenthalpy = np.interp(model.wellbores.Tinj.value,arraytinj,arrayhinj)


            # write doublet input file
            f = open(infile,'w', encoding='UTF-8')
            f.write('Doublet\n')
            f.write('MESHMAKER1----*----2----*----3----*----4----*----5----*----6----*----7----*----8\n')
            f.write('XYZ\n')
            f.write('	      0.\n')
            f.write('NX      50 %9.3f\n' % DeltaXgrid)
            f.write('NY      50 %9.3f\n' % DeltaYgrid)
            f.write('NZ       1 %9.3f\n' % DeltaZgrid)
            f.write('\n')
            f.write('\n')
            f.write('\n')
            f.write('ROCKS----1----*----2----*----3----*----4----*----5----*----6----*----7----*----8\n')
            f.write('POMED    3%10.1f %9.4f %9.2E %9.2E %9.2E %9.4f %9.2f          \n' % (rockdensity, rockpor, rockperm, rockperm, rockperm, rockthermalcond, rockheatcap))
            f.write('       0.0       0.0       2.0       0.0       0.0\n')
            f.write('    3            0.3      0.05\n')
            f.write('    8\n')
            f.write('\n')
            f.write('MULTI----1----*----2----*----3----*----4----*----5----*----6----*----7----*----8\n')
            f.write('    1    2    2    6\n')
            f.write('START----1----*----2----*----3----*----4----*----5----*----6----*----7----*----8\n')
            f.write('PARAM----1-MOP* 123456789012345678901234----*----5----*----6----*----7----*----8\n')
            f.write(' 8 19999       5000000000001  03 000   0                                        \n')
            f.write('       0.0 %9.3E 5259490.0       0.0                9.81       4.0       1.0\n' % (model.surfaceplant.plant_lifetime.value * 365 * 24 * 3600))
            f.write('    1.0E-5       1.0                 1.0       1.0          \n')
            f.write('           1000000.0          %10.1f\n' % initialtemp)
            f.write('                                                                                \n')
            f.write('SOLVR----1----*----2----*----3----*----4----*----5----*----6----*----7----*----8\n')
            f.write('3  Z1   O0       0.1    1.0E-6\n')
            f.write('\n')
            f.write('\n')
            f.write('GENER----1----*----2----*----3----*----4----*----5----*----6----*----7----*----8\n')
            f.write('%s  012                   1     COM1  %9.3f %9.1f          \n' % (injection_cell_id, flowrate, injenthalpy))
            f.write('%s  021                   1     MASS  %9.3f             \n' % (production_cell_id, -flowrate))
            f.write('\n')
            f.write('INCON----1----*----2----*----3----*----4----*----5----*----6----*----7----*----8\n')
            f.write('\n')
            f.write('FOFT ----1----*----2----*----3----*----4----*----5----*----6----*----7----*----8\n')
            f.write(f'{injection_cell_id}     \n')
            f.write(f'{production_cell_id}     \n')
            f.write('\n')
            f.write('GOFT ----1----*----2----*----3----*----4----*----5----*----6----*----7----*----8\n')
            f.write(f'{injection_cell_id}  012\n')
            f.write(f'{production_cell_id}  021\n')
            f.write('\n')
            f.write('ENDCY\n')
            f.close()
            print("GEOPHIRES will run TOUGH2 simulation with built-in Doublet model ...")

        else:
            infile = model.reserv.tough2modelfilename.value
            outfile = str('Doublet.out')
            print("GEOPHIRES will run TOUGH2 simulation with user-provided input file = "+model.reserv.tough2modelfilename.value+" ...")

        # run TOUGH2 executable
        try:
            os.system('%s  %s  %s' % (path_to_exe, infile, outfile))
        except:
            print("Error: GEOPHIRES could not run TOUGH2 and will abort simulation.")
            sys.exit()

        # read output temperature and pressure
        try:
            fname = f'FOFT_{production_cell_id}.csv'
            with open(fname, encoding='UTF-8') as f:
                first_line = f.readline()
                content = f.readlines()

            NumerOfResults = len(content)
            SimTimes = np.zeros(NumerOfResults)
            ProdPressure = np.zeros(NumerOfResults)
            ProdTemperature = np.zeros(NumerOfResults)

            for i in range(0,NumerOfResults):
                """
                #changed:   1>0'
                            8>1'
                            9>2'
                TODO - Audit index parameterization
                """
                SimTimes[i] = float(content[i].split(',')[0].strip('\n'))
                ProdPressure[i] = float(content[i].split(',')[1].strip('\n'))
                ProdTemperature[i] = float(content[i].split(',')[2].strip('\n'))



            model.reserv.Tresoutput.value = np.interp(model.reserv.timevector.value*365*24*3600,SimTimes,ProdTemperature)


            # Read FOFT and GOFT files
            import pandas as pd

            df = pd.read_csv(f'FOFT_{production_cell_id}.csv')
            dfG = pd.read_csv(f'GOFT_{production_cell_id}___021.csv')
            ef = pd.read_csv(f'FOFT_{injection_cell_id}.csv')
            efG = pd.read_csv(f'GOFT_{injection_cell_id}___012.csv')

            P0_production_well = df['              PRES'].iloc[0]
            Pf_production_well = df['              PRES'].iloc[-1]
            P0_injection_well = ef['              PRES'].iloc[0]
            Pf_injection_well = ef['              PRES'].iloc[-1]
            fr0_production_well = dfG['               GEN'].iloc[0]
            fr0_injection_well = efG['               GEN'].iloc[0]


            tough3_PI = fr0_production_well / (Pf_production_well - P0_production_well)
            tough3_II = fr0_injection_well / (Pf_injection_well - P0_injection_well)

            print("PI = ", tough3_PI)
            print("II = ", tough3_II)

            model.wellbores.PI.value = tough3_PI
            model.wellbores.II.value = tough3_II

        except Exception as e:
            raise RuntimeError(f'Error: GEOPHIRES could not import production temperature and pressure from TOUGH2'
                               f' output file ({infile}) and will abort simulation.') from e

        model.logger.info("Complete " + str(__class__) + ": " + sys._getframe().f_code.co_name)

        #print(SimTimes)
        #print(ProdPressure)
        #print(ProdTemperature)
        print(model.wellbores.PI.value)
        print(model.wellbores.II.value)



