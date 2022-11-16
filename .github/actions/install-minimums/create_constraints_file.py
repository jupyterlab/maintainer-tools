import sys

from packaging.requirements import Requirement
from pkginfo import Wheel

output_file = sys.argv[-2]
fname = sys.argv[-1]
constraints = set()

# Extract the minimum versions from the requirements in the wheel.
w = Wheel(fname)
for req in w.requires_dist:
    r = Requirement(req)
    for specifier in r.specifier:
        if "~" in specifier.operator or ">" in specifier.operator:
            spec = str(specifier).replace("~", "=")
            spec = spec.replace(">=", "==")
            spec = spec.replace(">", "==")
            constraints.add(f"{r.name}{spec}\n")

# Write the constraints to to a pip constraints file.
with open(output_file, "w") as fid:
    fid.writelines(constraints)
