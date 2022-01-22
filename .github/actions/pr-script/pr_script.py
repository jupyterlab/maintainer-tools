import json
import os
import shlex
import shutil
from pathlib import Path
from subprocess import CalledProcessError
from subprocess import check_output
from subprocess import PIPE

from ghapi.core import GhApi


def run(cmd, **kwargs):
    """Run a command as a subprocess and get the output as a string"""
    if not kwargs.pop("quiet", False):
        print(f"+ {cmd}")
    else:
        kwargs.setdefault("stderr", PIPE)

    parts = shlex.split(cmd)
    if "/" not in parts[0]:
        executable = shutil.which(parts[0])
        if not executable:
            msg = f'Could not find executable "{parts[0]}"'
            raise CalledProcessError(1, msg)
        parts[0] = executable

    try:
        return check_output(parts, **kwargs).decode("utf-8").strip()
    except CalledProcessError as e:
        print("output:", e.output.decode("utf-8").strip())
        if e.stderr:
            print("stderr:", e.stderr.decode("utf-8").strip())
        raise e


def run_script(target, script, commit_message=""):
    """Run a script on the target pull request URL"""
    # e.g. https://github.com/foo/bar/pull/81
    print("Checking for authorized user")
    association = os.environ.get("ASSOCIATION", "COLLABORATOR")
    if association not in ["COLLABORATOR", "MEMBER", "OWNER"]:
        raise ValueError(f"Cannot run for user with association {association}")
    print("User is authorized")

    print(f"Finding owner and repo for {target}")
    owner, repo = target.replace("https://github.com/", "").split("/")[:2]
    number = target.split("/")[-1]
    auth = os.environ["GITHUB_ACCESS_TOKEN"]

    print(f"Extracting PR {number} from {owner}/{repo}")
    gh = GhApi(owner=owner, repo=repo, token=auth)
    # here we get the target owner and branch so we can check it out below
    pull = gh.pulls.get(number)
    user_name = pull.head.repo.owner.login
    branch = pull.head.ref

    if Path("./test").exists():
        shutil.rmtree("./test")
    url = f"https://{maintainer}:{auth}@github.com/{user_name}/{repo}"
    run(f"git clone {url} -b {branch} test")
    os.chdir("test")
    run("pip install -e '.[test]'")
    for cmd in script:
        try:
            run(cmd)
        except Exception:
            continue

    # Use email address for the GitHub Actions bot
    # https://github.community/t/github-actions-bot-email-address/17204/6
    email = "41898282+github-actions[bot]@users.noreply.github.com"
    run(f"git config user.email {email}")
    run('git config user.name "GitHub Action"')
    message = commit_message or "Run maintainer script"
    opts = f"-m '{message}' -m 'by {maintainer}' -m '{json.dumps(script)}'"

    run(f"git commit -a {opts}")
    run(f"git push origin {branch}")


if __name__ == "__main__":
    # https://docs.github.com/en/actions/creating-actions/metadata-syntax-for-github-actions#inputs
    target = os.environ.get("TARGET")
    maintainer = os.environ["MAINTAINER"]
    commit_message = os.environ.get("COMMIT_MESSAGE", "")
    script = os.environ.get("SCRIPT", "[]")

    try:
        script = json.loads(script)
    except Exception:
        pass

    if not isinstance(script, list):
        script = [script]
    if os.environ.get("PRE_COMMIT") == "true":
        script += ["pre-commit run --all-files"]

    print(f"Running script on {target}:")
    print(f"   {script}")
    run_script(target, script, commit_message)
