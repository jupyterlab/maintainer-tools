#!/bin/bash
python -m venv $HOME/.venv
source $HOME/.venv/bin/activate

if [ "$PYTHON_PACKAGE_MANAGER" == "uv pip" ]; then
	uv pip install build packaging pkginfo
else
	pip install build packaging pkginfo
fi

SCRIPT_DIR=$(cd $(dirname "${BASH_SOURCE[0]}") && pwd)
python $SCRIPT_DIR/create_constraints_file.py $HOME/constraints.txt $(pwd)
cat $HOME/constraints.txt
echo "PIP_CONSTRAINT=$HOME/constraints.txt" >> $GITHUB_ENV
echo "UV_CONSTRAINT=$HOME/constraints.txt" >> $GITHUB_ENV
echo "UV_BUILD_CONSTRAINT=$HOME/constraints.txt" >> $GITHUB_ENV
