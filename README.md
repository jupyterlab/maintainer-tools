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
a script against a pull request. The script can only be run by a org member, collaborator, or repo owner if the association parameter is used (as in the examples below).

Note that the resulting commit will *not* trigger the
workflows to run again.  You will have to close/reopen the PR, or push another
commit for the workflows to run again.  If this behavior is not desirable,
you can use a personal access token instead of the default GitHub token provided
to the workflow. Make sure the token used is of as limited scope as possible (preferrably a bot account token with access to the `public_repo` scope only).

This first example allows maintainers to run `pre-commit` by commenting
"auto run pre-commit" on a Pull Request.


```yaml
name: Trigger Pre-Commit on a PR
on:
  issue_comment:
    types: [created]

permissions:
  contents: write
  pull-requests: write

jobs:
  pr-script:
    runs-on: ubuntu-latest
    steps:
      - uses: khan/pull-request-comment-trigger@1.0.0
        id: check
        with:
          trigger: "auto run pre-commit"
      - if: steps.check.outputs.triggered == 'true'
        uses: jupyterlab/maintainer-tools/.github/actions/base-setup@v1
      - if: steps.check.outputs.triggered == 'true'
        uses: jupyterlab/maintainer-tools/.github/actions/pr-script@v1
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          pre_commit: true
          commit_message: "auto run pre-commit"
          target: ${{ github.event.issue.html_url }}
          association: ${{ github.event.comment.author_association }}
```

In this example, the repo has a custom script that should be run, which is
triggered by a PR comment "auto run cleanup".  Again, this can only be run
by a org member, collaborator, or repo owner.


```yaml
name: Trigger a Cleanup Script on a PR
on:
  issue_comment:
    types: [created]

permissions:
  contents: write
  pull-requests: write

jobs:
  pr-script:
    runs-on: ubuntu-latest
    steps:
      - uses: khan/pull-request-comment-trigger@1.0.0
        id: check
        with:
          trigger: 'auto run cleanup'
      - if: steps.check.outputs.triggered == 'true'
        uses: jupyterlab/maintainer-tools/.github/actions/base-setup@v1
      - if: steps.check.outputs.triggered == 'true'
        uses: jupyterlab/maintainer-tools/.github/actions/pr-script@v1
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          script: "[\"jlpm run integrity\", \"jlpm run lint\"]"
          commit_message: "auto run cleanup"
          target:  ${{ github.event.issue.html_url }}
          association: ${{ github.event.comment.author_association }}
```

## Update snapshots

You can use _update snapshots_ action to commit on a branch 
[Playwright](https://playwright.dev) updated snapshots.

The requirements and constrains are:
- You must be on the branch to which the snapshots will be committed
- You must installed your project before calling the action
- The action is using `yarn` package manager
- The Playwright tests must be in TypeScript or JavaScript

An example of workflow that get triggered when a PR comment contains 
_update playwright snapshots_ would be:

```yaml
name: Update Playwright Snapshots

on:
  issue_comment:
    types: [created, edited]

permissions:
  contents: write
  pull-requests: write

jobs:
  update-snapshots:
    if: ${{ github.event.issue.pull_request && contains(github.event.comment.body, 'update playwright snapshots') }}
    runs-on: ubuntu-latest

    steps:
      - name: Checkout
        uses: actions/checkout@v2

      - name: Checkout the branch from the PR that triggered the job
        run: |
          # PR branch remote must be checked out using https URL
          git config --global hub.protocol https
          hub pr checkout ${{ github.event.issue.number }}
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}

      - name: Install your project
        run: |
          # Execute the required installation command

      - name: Update snapshots
        uses: jupyterlab/maintainer-tools/.github/actions/update-snapshots@v1
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          # Test folder within your repository
          test_folder: playwright-tests
          # Server url to wait for before updating the snapshots
          #  See specification for https://github.com/iFaxity/wait-on-action `resource`
          server_url: http-get://localhost:8888
          # Optional npm scripts (the default values are displayed)
          start_server_script: start
          update_script: test:update
```
