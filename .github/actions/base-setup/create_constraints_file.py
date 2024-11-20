import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, List, cast

from build.util import project_wheel_metadata  # type:ignore[import-not-found]
from packaging.requirements import Requirement

if TYPE_CHECKING:
    # not importing this at runtime as it is only exposed in Python 3.10+
    # (although the interface was already followed in earlier versions)
    from importlib.metadata import PackageMetadata  # type:ignore[attr-defined]
else:
    PackageMetadata = Any

output_file = sys.argv[-2]
top_level_project_dir = sys.argv[-1]
constraints = {}


def extract_dependencies(project_dir: str) -> List[str]:
    reqs = []
    print(f"Extracting metadata from wheel for {project_dir}...")
    metadata = project_wheel_metadata(source_dir=project_dir)
    reqs.extend(get_requires_dist(metadata))

    # extract requirements from local dependencies specified with file: protocol
    # to support the mono-repo usecase
    local_projects = {}
    for req in reqs:
        r = Requirement(req)
        if r.url and r.url.startswith("file://"):
            path = r.url.replace("file://", "")
            local_projects[r.name] = path

    reqs_from_local_dependencies = []
    for dependency_name, path in local_projects.items():
        print(f"Discovering constraints in local {dependency_name} package under {path}")
        sub_dependencies = extract_dependencies(path)
        # filter out dependencies between local packages (e.g. jupyter-ai depends on
        # a fixed minimum version of `jupyter-ai-magics`, but here we want to test
        # the latest version against its third-party dependencies - not the old one).
        sub_dependencies = [
            req for req in sub_dependencies if Requirement(req).name not in local_projects
        ]
        reqs_from_local_dependencies.extend(sub_dependencies)
    return reqs + reqs_from_local_dependencies


def get_requires_dist(metadata: PackageMetadata) -> List[str]:
    return cast(List[str], metadata.get_all("Requires-Dist")) or []


reqs = extract_dependencies(top_level_project_dir)

for req in reqs:
    r = Requirement(req)
    for specifier in r.specifier:
        if "!" in specifier.operator:
            continue
        if "~" in specifier.operator or ">" in specifier.operator:
            spec = str(specifier).replace("~", "=")
            spec = spec.replace(">=", "==")
            spec = spec.replace(">", "==")
            constraints[r.name] = spec

constraints_list = [f"{key}{value}\n" for (key, value) in constraints.items()]

# Write the constraints to to a pip constraints file.
with Path(output_file).open("w") as fid:
    fid.writelines(constraints_list)
