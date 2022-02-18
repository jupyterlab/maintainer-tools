import sys
from pkginfo import Wheel
from packaging.requirements import Requirement

fname = sys.argv[-1]
constraints = []

# Extract the minimum versions from the requirements in the wheel.
w = Wheel(fname)
for req in w.requires_dist:
    r = Requirement(req)
    for specifier in r.specifier:
        if '~' in specifier.operator or ">" in specifier.operator:
            spec = str(specifier).replace('~', '=')
            spec = spec.replace('>=', '==')
            spec = spec.replace('>', '==')
            constraints.append(f"{r.name}{spec}")

# Write the constraints to to a pip constraints file.
with open('contraints_file.txt', 'w') as fid:
    fid.writelines(constraints)
