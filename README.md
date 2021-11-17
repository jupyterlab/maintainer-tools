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
