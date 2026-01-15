#!/bin/zsh

set -e
cd "$(dirname "$0")"

# Use this script to regenerate example results in cases where changes in GEOPHIRES
# calculations alter the example test output. Example:
# ./tests/regenerate-example-result.sh SUTRAExample1
# See https://github.com/NREL/GEOPHIRES-X/issues/107

# Note: make sure your virtualenv is activated and you have run pip install -e . before running or this script will fail
# or generate incorrect results.

python -mgeophires_x examples/$1.txt examples/$1.out
rm examples/$1.json

if [[ $1 == "example1_addons" ]]
then
    echo "Updating CSV..."
    python regenerate_example_result_csv.py example1_addons
fi

if [[ $1 == "Fervo_Project_Cape-5" ]]
then
    python ../src/geophires_docs/generate_fervo_project_cape_5_docs.py

    echo "Regenerating Fervo_Project_Cape-6..."

    sed -e 's/Construction Years,.*/Construction Years, 3/' \
        -e 's/^Number of Production Wells,.*/Number of Production Wells, 12/' \
        -e 's/500 MWe/100 MWe/' \
        -e 's/Phase II/Phase I/' \
        examples/Fervo_Project_Cape-5.txt > examples/Fervo_Project_Cape-6.txt

    python -mgeophires_x examples/Fervo_Project_Cape-6.txt examples/Fervo_Project_Cape-6.out
    rm examples/Fervo_Project_Cape-6.json

    if [ ! -f regenerate-example-result.env ] && [ -f regenerate-example-result.env.template ]; then
        echo "Creating regenerate-example-result.env from template..."
        cp regenerate-example-result.env.template regenerate-example-result.env
    fi

    source regenerate-example-result.env
    if [ -n "$GEOPHIRES_FPC5_SENSITIVITY_ANALYSIS_PROJECT_ROOT" ]; then
        echo "Updating sensitivity analysis..."
        STASH_PWD=$(pwd)
        cd $GEOPHIRES_FPC5_SENSITIVITY_ANALYSIS_PROJECT_ROOT
        source venv/bin/activate
        python -m fpc_sensitivity_analysis.generate_geophires_fpc5_sensitivity_analysis
        deactivate
        cd $STASH_PWD
    fi
fi
