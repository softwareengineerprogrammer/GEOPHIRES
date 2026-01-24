import os


def _get_file_path(file_name: str) -> str:
    return os.path.join(os.path.abspath(os.path.dirname(__file__)), str(file_name))


if __name__ == '__main__':
    print('Syncing example5b.txt from example5.txt and Examples/ReservoirOutput.txt...')

    # 1. Read ReservoirOutput.txt and extract temperature values
    reservoir_output_path = _get_file_path('../src/geophires_x/Examples/ReservoirOutput.txt')
    temperatures = []
    with open(reservoir_output_path) as f:
        for line in f:
            line = line.strip()
            if line:
                # Each line has format: "time , temperature"
                parts = line.split(',')
                if len(parts) >= 2:
                    temp = parts[1].strip()
                    temperatures.append(temp)

    # 2. Update examples/example5b.txt with the new Reservoir Output Profile
    example5b_path = _get_file_path('examples/example5b.txt')
    reservoir_output_profile_value = ','.join(temperatures)

    with open(example5b_path) as f:
        lines = f.readlines()

    with open(example5b_path, 'w') as f:
        for line in lines:
            if line.startswith('Reservoir Output Profile,'):
                # Replace the line with updated temperature profile
                f.write(f'Reservoir Output Profile, {reservoir_output_profile_value}\n')
            else:
                f.write(line)

    print(f'Updated example5b.txt with {len(temperatures)} temperature values from ReservoirOutput.txt')
