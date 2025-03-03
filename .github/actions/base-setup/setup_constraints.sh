#!/bin/bash
python -m venv $HOME/.venv
source $HOME/.venv/bin/activate
pip install build packaging pkginfo
mkdir $HOME/dist
python -m build --outdir $HOME/dist --wheel .

SCRIPT_DIR=$(cd $(dirname "${BASH_SOURCE[0]}") && pwd)
python $SCRIPT_DIR/create_constraints_file.py $HOME/constraints.txt $HOME/dist/*.whl
cat $HOME/constraints.txt
echo "PIP_CONSTRAINT=$HOME/constraints.txt" >> $GITHUB_ENV
