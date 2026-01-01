#!/bin/zsh


# Use this script to regenerate example results in cases where changes in GEOPHIRES
# calculations alter the example test output. Example:
# ./tests/regenerate-example-result.sh SUTRAExample1
# See https://github.com/NREL/GEOPHIRES-X/issues/107

# Note: make sure your virtualenv is activated before running or this script will fail
# or generate incorrect results.

cd "$(dirname "$0")"
python -mgeophires_x examples/$1.txt examples/$1.out
rm examples/$1.json

if [[ $1 == "example1_addons" ]]
then
    echo "Updating CSV..."
    python regenerate_example_result_csv.py example1_addons
fi

if [[ $1 == "Fervo_Project_Cape-4" ]]
then
    if [ ! -f regenerate-example-result.env ] && [ -f regenerate-example-result.env.template ]; then
        echo "Creating regenerate-example-result.env from template..."
        cp regenerate-example-result.env.template regenerate-example-result.env
    fi

    source regenerate-example-result.env
    if [ -n "$GEOPHIRES_FPC4_SENSITIVITY_ANALYSIS_PROJECT_ROOT" ]; then
        echo "Updating sensitivity analysis..."
        STASH_PWD=$(pwd)
        cd $GEOPHIRES_FPC4_SENSITIVITY_ANALYSIS_PROJECT_ROOT
        source venv/bin/activate
        python -m fpc4_sensitivity_analysis
        deactivate
        cd $STASH_PWD
    fi

    # TODO regenerate Fervo_Project_Cape-5 by copying Fervo_Project_Cape-4.txt
    #  and substituting Construction Years = 3 and Number of Doublets = 10
fi
