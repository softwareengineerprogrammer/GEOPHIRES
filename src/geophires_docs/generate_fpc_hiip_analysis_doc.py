import logging
import shutil
from pathlib import Path

from jinja2 import Environment
from jinja2 import FileSystemLoader

from geophires_monte_carlo import GeophiresMonteCarloClient
from geophires_monte_carlo import MonteCarloRequest
from geophires_monte_carlo import SimulationProgram
from hip_ra import HipRaInputParameters
from hip_ra_x import HipRaXClient

_log = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_BUILD_DIR = _PROJECT_ROOT / 'build' / 'fpc_hiip_analysis'
_IMAGES_DIR = _PROJECT_ROOT / 'docs' / '_images'


def generate_fpc_hiip_analysis_doc():
    _BUILD_DIR.mkdir(parents=True, exist_ok=True)
    _IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Define and Run Deterministic Baseline
    base_params = {
        'Reservoir Temperature': 199.0,
        'Rejection Temperature': 80.0,
        'Reservoir Porosity': 0.0,
        'Reservoir Area': 48.0,
        'Reservoir Thickness': 4.0,
        'Reservoir Life Cycle': 30,
        'Rock Heat Capacity': 2.212e12,
        'Fluid Specific Heat Capacity': -1.0,
        'Density Of Reservoir Fluid': -1.0,
        'Density Of Reservoir Rock': 2.8e12,
        'Recoverable Heat from Rock': 1.0,
        'Recoverable Fluid Factor': 1.0,
        'Print Output to Console': False,
    }

    base_input_path = _BUILD_DIR / 'fpc_hiip_base.txt'
    with open(base_input_path, 'w') as f:
        for k, v in base_params.items():
            f.write(f'{k}, {v}\n')

    _log.info('Running deterministic HIP-RA-X baseline...')
    client = HipRaXClient()
    det_result = client.get_hip_ra_result(HipRaInputParameters(file_path_or_params_dict=base_input_path))

    # Parse deterministic outputs
    det_stored_heat_kj = 0.0
    det_elec_mw = 0.0
    with open(det_result.output_file_path) as f:
        for line in f:
            if 'Stored Heat (reservoir):' in line:
                det_stored_heat_kj = float(line.split(':')[1].strip().split(' ')[0])
            if 'Producible Electricity (reservoir):' in line:
                det_elec_mw = float(line.split(':')[1].strip().split(' ')[0])

    # Convert kJ to 10^15 Joules (10^15 J = 10^12 kJ)
    det_stored_heat_15j = det_stored_heat_kj / 1e12

    # 2. Configure and Run Monte Carlo Simulation
    mc_settings_path = _BUILD_DIR / 'fpc_hiip_mc_settings.txt'
    mc_output_path = _BUILD_DIR / 'fpc_hiip_mc_results.txt'

    with open(mc_settings_path, 'w') as f:
        f.write('INPUT, Reservoir Temperature, uniform, 170.0, 250.0\n')
        f.write('OUTPUT, Stored Heat (reservoir)\n')
        f.write('OUTPUT, Producible Electricity (reservoir)\n')
        f.write('ITERATIONS, 1000\n')
        f.write(f'MC_OUTPUT_FILE, {mc_output_path.absolute()}\n')

    _log.info('Running Monte Carlo HIP-RA-X simulation (170°C - 250°C)...')

    # Initialize the Monte Carlo Request
    mc_request = MonteCarloRequest(
        simulation_program=SimulationProgram.HIP_RA_X,
        input_file=base_input_path.absolute(),
        monte_carlo_settings_file=mc_settings_path.absolute(),
        output_file=mc_output_path.absolute(),
    )

    # Execute the client
    mc_client = GeophiresMonteCarloClient()
    mc_result = mc_client.get_monte_carlo_result(mc_request)

    # 3. Read MC JSON Results directly from the result object
    mc_stats = mc_result.result['output']

    mc_stored_heat_mean_kj = mc_stats['Stored Heat (reservoir)']['mean']
    mc_stored_heat_mean_15j = mc_stored_heat_mean_kj / 1e12

    # Copy generated MC histogram images to the docs directory
    mc_temp_img_src = _BUILD_DIR / 'Reservoir Temperature.png'
    mc_heat_img_src = _BUILD_DIR / 'Stored Heat (reservoir).png'

    mc_temp_img_dst = _IMAGES_DIR / 'fpc_hiip_mc_Reservoir_Temperature.png'
    mc_heat_img_dst = _IMAGES_DIR / 'fpc_hiip_mc_Stored_Heat.png'

    if mc_temp_img_src.exists():
        shutil.copy(mc_temp_img_src, mc_temp_img_dst)
        _log.info(f'Copied {mc_temp_img_src.name} to docs/_images/')
    if mc_heat_img_src.exists():
        shutil.copy(mc_heat_img_src, mc_heat_img_dst)
        _log.info(f'Copied {mc_heat_img_src.name} to docs/_images/')

    # 4. Render Jinja Template
    _log.info('Rendering Markdown documentation...')
    docs_dir = _PROJECT_ROOT / 'docs'

    template_values = {
        'det_stored_heat_15j': f'{det_stored_heat_15j:,.0f}',
        'det_elec_mw': f'{det_elec_mw:,.0f}',
        'mc_stored_heat_mean_15j': f'{mc_stored_heat_mean_15j:,.0f}',
    }

    env = Environment(loader=FileSystemLoader(docs_dir), autoescape=True)
    template = env.get_template('FPC_HIIP_Analysis.md.jinja')
    output = template.render(**template_values)

    output_file = docs_dir / 'FPC_HIIP_Analysis.md'
    output_file.write_text(output, encoding='utf-8')
    _log.info(f'✓ Generated {output_file}')


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    generate_fpc_hiip_analysis_doc()
