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

Use this action to consolidate setup steps and caching in your workflows.  You can control the versions of Python and Node used by setting `matrix.python-version` and `matrix.node-version`, respectively.
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

## PR Binder Link

Use this action to add binder links for testing PRs, which show up as a comment.  
You can use the optional `url_path` parameter to use a different url than the default `lab`.
An example workflow would be:


```yaml
name: Binder Badge
on:
  pull_request_target:
    types: [opened]

jobs:
  binder:
    runs-on: ubuntu-latest
    permissions:
      pull-requests: write
    steps:
      - uses: jupyterlab/maintainer-tools/.github/actions/binder-link@v1
        with:
          github_token: ${{ secrets.github_token }}
```

## PR Script

You can use the PR Script action in your repo along with [pull-request-comment-trigger](https://github.com/Khan/pull-request-comment-trigger) to enable maintainers to comment on PRs to run
a script against a pull request.  In this example, the maintainer can write the
comment "auto run pre-commit", and `pre-commit` will be run against the PR::


```yaml
name: Trigger Pre-Commit on a PR
on:
  issue_comment:
    types: [created]
jobs:
  pr-script:
    runs-on: ubuntu-latest
    steps:
      - uses: khan/pull-request-comment-trigger@1.0.0
        id: check
          with:
            trigger: 'auto run pre-commit'
      - if: steps.check.outputs.triggered == 'true'
        uses: jupyterlab/maintainer-tools/.github/actions/pr-script@v1
        with:
          token: ${{ secrets.GITHUB_TOKEN }}
          pre_commit: true
          commit_message: "auto run pre-commit"
          target: ${{ github.event.issue_url }}
```

In this example, the maintainer can write the
comment "auto run script <foo>", and the script will be run against the PR.
The script can be a list, such as `["jlpm run integrity", "jlpm run lint"]`.


```yaml
name: Run a Script against a PR
on:
  issue_comment:
    types: [created]
jobs:
  pr-script:
    runs-on: ubuntu-latest
    steps:
      - uses: khan/pull-request-comment-trigger@1.0.0
        id: check
          with:
            trigger: 'auto run script'
      - if: steps.check.outputs.triggered == 'true'
        uses: jupyterlab/maintainer-tools/.github/actions/pr-script@v1
        with:
          token: ${{ secrets.GITHUB_TOKEN }}
          script: ${{ steps.check.outputs.comment_body }}
          script_prefix: 'auto run script'
          commit_message: "auto run script"
          target: ${{ github.event.issue_url }}
```
