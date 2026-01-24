import argparse
import os

RESERVOIR_OUTPUT_PROFILE_PARAM_NAME = 'Reservoir Output Profile'
RESERVOIR_MODEL_PARAM_NAME = 'Reservoir Model'


def _get_file_path(file_name: str) -> str:
    return os.path.join(os.path.abspath(os.path.dirname(__file__)), str(file_name))


def _is_numeric(value: str) -> bool:
    """Check if a string value can be converted to a float."""
    try:
        float(value)
        return True
    except ValueError:
        return False


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Regenerate a CSV result file from a GEOPHIRES-X example .out file.')
    parser.add_argument(
        'example_id',
        type=str,
        nargs='?',  # Makes the argument optional
        default='example5b',
        help='The base name of the example file',
    )
    parser.add_argument(
        'reservoir_output_source_file',
        type=str,
        nargs='?',  # Makes the argument optional
        default='src/geophires_x/Examples/ReservoirOutput.txt',
        help='Path to reservoir source file relative to project root',
    )
    args = parser.parse_args()

    reservoir_output_source_file = args.reservoir_output_source_file
    example_file_name = f'{args.example_id}.txt'
    print(f'Syncing {example_file_name} {RESERVOIR_OUTPUT_PROFILE_PARAM_NAME} from {reservoir_output_source_file}...')

    # 1. Read ReservoirOutput.txt and extract temperature values
    reservoir_output_path = _get_file_path(f'../{reservoir_output_source_file}')
    temperatures = []
    with open(reservoir_output_path) as f:
        for line in f:
            line = line.strip()
            if line:
                # Each line has format: "time , temperature"
                parts = line.split(',')
                if len(parts) >= 2:
                    temp = parts[1].strip()
                    # Skip header rows by checking if the value is numeric
                    if _is_numeric(temp):
                        temperatures.append(temp)

    # 2. Update example file with the new Reservoir Output Profile
    example_path = _get_file_path(f'examples/{example_file_name}')
    reservoir_output_profile_value = ','.join(temperatures)
    reservoir_output_profile_line = f'{RESERVOIR_OUTPUT_PROFILE_PARAM_NAME}, {reservoir_output_profile_value}\n'

    with open(example_path) as f:
        lines = f.readlines()

    # Check if RESERVOIR_OUTPUT_PROFILE_PARAM_NAME already exists in the file
    profile_exists = any(line.startswith(f'{RESERVOIR_OUTPUT_PROFILE_PARAM_NAME},') for line in lines)

    with open(example_path, 'w') as f:
        for line in lines:
            if line.startswith(f'{RESERVOIR_OUTPUT_PROFILE_PARAM_NAME},'):
                # Replace the existing line with updated temperature profile
                f.write(reservoir_output_profile_line)
            elif not profile_exists and line.startswith(f'{RESERVOIR_MODEL_PARAM_NAME},'):
                # Write the Reservoir Model line first
                f.write(line)
                # Insert the Reservoir Output Profile line after Reservoir Model
                f.write(reservoir_output_profile_line)
            else:
                f.write(line)

    print(
        f'Updated {example_file_name} {RESERVOIR_OUTPUT_PROFILE_PARAM_NAME} '
        f'with {len(temperatures)} temperature values from {reservoir_output_source_file}'
    )
