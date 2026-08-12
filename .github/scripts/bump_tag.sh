set -eux

# Move the major version tag (v1, v2, ...) which GitHub Actions consumers follow instead of
# pinning every release. Derived from the version rather than written out, so that releasing a
# new major stops dragging the previous major's tag onto it.
if [[ ${RH_DRY_RUN:=true} != 'true' ]]; then
    major="v$(python -c "import json, pathlib; print(json.loads(pathlib.Path('package.json').read_text())['version'].split('.')[0])")"
    git tag -f -a "${major}" -m "Github Action release"
    git push origin -f --tags
fi
