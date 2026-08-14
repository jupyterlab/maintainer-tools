set -eux

# Move the major version tag (v1, v2, ...) which GitHub Actions consumers follow instead of
# pinning every release. Derived from the version rather than written out, so that releasing a
# new major stops dragging the previous major's tag onto it.
if [[ ${RH_DRY_RUN:=true} != 'true' ]]; then
    version="$(python -c 'import json, pathlib; print(json.loads(pathlib.Path("package.json").read_text())["version"])')"
    major="v${version%%.*}"

    # Consumers follow v1, which predates 1.0 and never matched the 0.x line. Moving v0 instead
    # would leave all of them on the last 0.x release without anything saying so.
    if [[ ${major} == 'v0' ]]; then
        echo "Refusing to move ${major} for version ${version}: release 1.0.0 or later." >&2
        exit 1
    fi

    git tag -f -a "${major}" -m "Github Action release"
    # populate-release has already pushed the release tag, so only the moved major tag is left.
    # Forcing every tag would risk overwriting unrelated ones on the remote.
    git push origin --force "refs/tags/${major}"
fi
