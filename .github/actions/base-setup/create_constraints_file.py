import sys
from pathlib import Path
from zipfile import ZipFile

from packaging.requirements import Requirement

output_file = sys.argv[-2]
fname = sys.argv[-1]
constraints = {}

archive = ZipFile(fname)
reqs = []
for f in archive.namelist():
    if f.endswith("METADATA"):
        for li in archive.open(f).read().decode("utf-8").split("\n"):
            if li.startswith("Requires-Dist"):
                reqs.append(li.replace("Requires-Dist: ", ""))
archive.close()

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
