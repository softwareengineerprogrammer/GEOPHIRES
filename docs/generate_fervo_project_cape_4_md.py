#!python
"""
Script to generate Fervo_Project_Cape-4.md from its jinja template.
This ensures the markdown documentation stays in sync with actual GEOPHIRES results.
"""

import sys
from pathlib import Path
from typing import Any

from jinja2 import Environment
from jinja2 import FileSystemLoader
from pint.facets.plain import PlainQuantity

from geophires_x.GeoPHIRESUtils import sig_figs
from geophires_x_client import GeophiresXResult

# Add project root to path to import GEOPHIRES modules
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / 'src'))


def get_result_values(result: GeophiresXResult):

    def _q(d: dict[str, Any]) -> PlainQuantity:
        return PlainQuantity(d['value'], d['unit'])

    r: dict[str, dict[str, Any]] = result.result
    return {
        'lcoe_usd_per_mwh': sig_figs(
            _q(r['SUMMARY OF RESULTS']['Electricity breakeven price']).to('USD / MWh').magnitude, 3
        ),
        'irr_pct': sig_figs(r['ECONOMIC PARAMETERS']['After-tax IRR']['value'], 3),
        'npv_musd': sig_figs(r['ECONOMIC PARAMETERS']['Project NPV']['value'], 3),
        # TODO port all input and result values here instead of hardcoding them in the template
    }


def main():
    """
    Generate Fervo_Project_Cape-4.md (markdown documentation) from the Jinja template.
    """

    result = GeophiresXResult(project_root / 'tests/examples/Fervo_Project_Cape-4.out')

    print('Extracting result values...')
    result_values = get_result_values(result)

    # Set up Jinja environment
    docs_dir = project_root / 'docs'
    env = Environment(loader=FileSystemLoader(docs_dir), autoescape=True)
    template = env.get_template('Fervo_Project_Cape-4.md.jinja')

    # Render template
    print('Rendering template...')
    output = template.render(**result_values)

    # Write output
    output_file = docs_dir / 'Fervo_Project_Cape-4.md'
    output_file.write_text(output)

    print(f'✓ Generated {output_file}')
    print('\nKey results:')
    print(f"\tLCOE: {result_values['lcoe_usd_per_mwh']}")
    print(f"\tIRR: {result_values['irr_pct']}")
    # print(f"  Total CAPEX: {result_values['capex']}")  # TODO


if __name__ == '__main__':
    main()
