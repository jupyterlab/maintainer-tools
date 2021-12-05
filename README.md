# maintainer-tools

## Workflows

Workflows for use by maintainers.  These should be run from your fork of this repository, with
an [encrypted secret](https://docs.github.com/en/actions/security-guides/encrypted-secrets) called
`ACCESS_TOKEN` that is a [personal access token](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/creating-a-personal-access-token) with `repo` and `workflow`
scopes.

### PR Script

The PR Script Workflow allows you to make a commit against a PR as a maintainer without having
to check out the PR locally and push the change.  The manual workflow takes as its inputs a link to the PR
and a comma-separated list of quoted commands to run.  As a convenience, you can also type "True" for the
option to run pre-commit against the PR to fix up any pre-commit errors.


## Actions

## Base Setup

Use this action to consolidate setup steps in your workflows.  You can control the versions of Python and Node used by setting `matrix.python-version` and `matrix.node-version`, respectively.
An example workflow file would be:

```yaml
name: Tests
on:
  push:
    branches: "main"
  pull_request:
    branches: "*"
jobs:
  build:
    runs-on: ubuntu-latest
  steps:
    - name: Checkout
      uses: actions/checkout@v2
    - name: Base Setup
      uses: jupyterlab/maintainer-tools/.github/actions/base-setup@v1
    - name: Install
      shell: bash
      run: pip install -e ".[test]"
    - name: Test
      shell: bash
      run: pytest
```

## Enforce Labels

Use this action to enforce one of the triage labels on PRs in your repo (one of `documentation`, `bug`, `enhancement`, `feature`, `maintenance`).  An example workflow file would be:

```yaml
name: Enforce PR label

on:
  pull_request:
    types: [labeled, unlabeled, opened, edited, synchronize]
jobs:
  enforce-label:
    runs-on: ubuntu-latest
    steps:
      - name: enforce-triage-label
        uses: jupyterlab/maintainer-tools/.github/actions/enforce-label@v1
```

## Test Downstream Libraries

Use this action to test a package against downstream libraries.  This can be used to catch breaking changes prior to merging them. An example workflow file would be:


```yaml
name: Downstream Tests
on:
  push:
    branches: "main"
  pull_request:
    branches: "*"
jobs:
  build:
    runs-on: ubuntu-latest
  steps:
    - name: Checkout
      uses: actions/checkout@v2
    - name: Base Setup
      uses: jupyterlab/maintainer-tools/.github/actions/base-setup@v1
    - name: Test Against Foo
      uses: jupyterlab/maintainer-tools/.github/actions/downstream-test@v1
      with:
        package_name: foo
    - name: Test Against Bar
      uses: jupyterlab/maintainer-tools/.github/actions/downstream-test@v1
      with:
        package_name: bar
        env_values: "FIZZ=buzz NAME=snuffy"
```
