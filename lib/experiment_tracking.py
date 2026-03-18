import asyncio
import os
import posixpath
import subprocess
import threading
import time
from datetime import datetime
from functools import partial
from pathlib import Path

import git
from inspect_ai.log import list_eval_logs, read_eval_log
from inspect_ai.model import GenerateConfig, get_model
from termcolor import colored
from tqdm import tqdm


def _resolve_s3_bucket_and_project(log_dir: str) -> str:
    bucket_key = "S3_BUCKET"
    project_key = "S3_PROJECT"
    log_dir = log_dir.replace("$" + bucket_key, os.environ[bucket_key])
    log_dir = log_dir.replace("$" + project_key, os.environ[project_key])
    return log_dir


def _get_repo_diff(repo_path=".") -> str:
    """Get the diff of all changes (staged and unstaged) in a repo as a string."""
    result = subprocess.run(
        ["git", "-C", repo_path, "diff", "HEAD"], capture_output=True, text=True
    )
    return result.stdout


def _generate_commit_message() -> str:
    diff = _get_repo_diff()
    prompt = (
        "write a <10 word summary of the diff, output nothing else:\n\n<diff>\n"
        + diff
        + "\n</diff>"
    )
    model_output = asyncio.run(
        get_model("anthropic/claude-sonnet-4-5-20250929").generate(
            prompt, config=GenerateConfig(max_tokens=20)
        )
    )
    return model_output.completion


def _find_repo_root(start_path="."):
    """Find the git repository root by searching upwards from start_path."""
    current = Path(start_path).resolve()
    while current != current.parent:
        if (current / ".git").exists():
            return str(current)
        current = current.parent
    # If not found, try current directory
    return str(Path(start_path).resolve())


def _has_git_changes(repo_path=None):
    try:
        if repo_path is None:
            repo_path = _find_repo_root()
        repo = git.Repo(repo_path)
        return repo.is_dirty(untracked_files=True)
    except (git.InvalidGitRepositoryError, Exception):
        return False


def _get_github_webview_url(repo_path=None, remote_name="origin") -> str:
    if repo_path is None:
        repo_path = _find_repo_root()
    repo = git.Repo(repo_path)
    remote = repo.remote(remote_name)
    url = remote.url

    # Convert SSH URL to HTTPS if needed
    if url.startswith("git@"):
        url = url.replace("git@", "https://")
        url = url.replace(".com:", ".com/")

    # Remove .git suffix if present
    if url.endswith(".git"):
        url = url[:-4]

    # Ensure it's using HTTPS
    if url.startswith("http://"):
        url = url.replace("http://", "https://")

    # Get the current commit hash
    current_hash = repo.head.commit.hexsha

    # GitHub format: https://github.com/owner/repo/tree/hash
    permalink = f"{url}/tree/{current_hash}"

    return permalink


def _get_current_branch(repo_path=None) -> str:
    if repo_path is None:
        repo_path = _find_repo_root()
    repo = git.Repo(repo_path)
    return repo.active_branch.name


def _get_latest_commit_message(repo_path=None):
    if repo_path is None:
        repo_path = _find_repo_root()
    result = subprocess.run(
        ["git", "log", "-1", "--pretty=%B"],
        capture_output=True,
        text=True,
        check=True,
        cwd=repo_path,
    )
    return result.stdout.strip()


def _git_push(skip_ai_commit_suggestion: bool = False, repo_path=None):
    if repo_path is None:
        repo_path = _find_repo_root()
    if not skip_ai_commit_suggestion:
        suggestion = _generate_commit_message()
        print("Suggested commit message:", colored(suggestion, "cyan"))
        msg = input("Enter commit message (or leave blank to accept suggestion): ")
        if msg.strip() == "":
            msg = suggestion
    else:
        msg = input("Enter commit message: ")
    subprocess.run(["git", "add", "."], check=True, cwd=repo_path)
    subprocess.run(["git", "commit", "-m", msg], check=True, cwd=repo_path)
    subprocess.run(["git", "push"], check=True, cwd=repo_path)



def auto_push_working_changes(
    auto_push: bool = True, ignore_unstaged: bool = False
) -> None:
    """Automatically commit and push working changes to the current git branch.

    Args:
        auto_push: If True, automatically commit and push changes. If False, abort with a warning.
        ignore_unstaged: If True, skip checking for unstaged changes and proceed without pushing.
    """
    # check if there are working changes:
    if _has_git_changes() and not ignore_unstaged:
        if auto_push:
            if _get_current_branch() == "main":
                print(colored("Cannot push directly to main branch!", "red"))
                print("Aborting!")
                exit(1)
            else:
                _git_push()
        else:
            print(
                colored(
                    "You have unstaged working changes. You can push these changes automatically with the --push flag or ignore working changes with --ignore-unstaged",
                    "yellow",
                )
            )
            print("Aborting!")
            exit(1)


def generate_log_dir(log_dir_base: str) -> str:
    """Generate a timestamped log directory path.

    Creates a log directory path by appending a timestamp to the base directory path.
    Uses POSIX path joining to ensure compatibility with S3 paths.

    Args:
        log_dir_base: Base directory path for logs (e.g., 's3://bucket/path/to/logs').

    Returns:
        Complete log directory path with timestamp (e.g., 's3://bucket/path/to/logs/20231015_143022').
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_dir = posixpath.join(log_dir_base, timestamp)
    return log_dir


def show_progress_bar_for_eval_set(log_dir: str, expected_count: int):
    """Display a progress bar for eval_set() execution by monitoring log files.

    Spawns a daemon thread that monitors the log directory and updates a tqdm progress bar
    as tasks complete. The progress bar counts tasks that reach a terminal state
    (success, cancelled, or error).

    Args:
        log_dir: Path to the directory where evaluation logs are being written.
            Can be a local path or S3 path (e.g., 's3://bucket/path/to/logs').
        expected_count: Total number of tasks expected to complete.

    Note:
        The monitoring thread runs as a daemon and will automatically terminate when
        the main thread exits. Progress is updated every second by checking log file
        headers.
    """

    def _retry_call(func, num_retries=10, delay=3):
        for _ in range(num_retries):
            try:
                return func()
            except Exception:
                time.sleep(delay)
        raise RuntimeError("progress bar failed to read eval files")

    def _count_done() -> int:
        # count succeeded tasks
        done = 0
        for log_file in list_eval_logs(log_dir):
            log = _retry_call(partial(read_eval_log, log_file, header_only=True))
            if log.status in ["success", "cancelled", "error"]:
                done += 1
            log.location
        return done

    def _pbar_thread() -> None:
        prev_done = 0
        with tqdm(total=expected_count) as pbar:
            while True:
                done = _count_done()
                pbar.update(max(0, done - prev_done))
                if done >= expected_count:
                    break
                prev_done = done
                time.sleep(1)

    # kick off daemon thread that will die along with the main thread:
    threading.Thread(target=_pbar_thread, daemon=True).start()


def start_background_s3_uploader(log_dir: str, bucket: str) -> None:
    """Start a background thread that uploads completed evals to S3.

    Monitors the log directory for completed .eval files and uploads them
    to structured S3 storage as they finish.

    Args:
        log_dir: Local path to the directory where evaluation logs are being written.
        bucket: S3 bucket name.
    """
    from lib.eval_storage import upload_eval

    uploaded_files: set[str] = set()
    print(f"[S3 Uploader] Started background uploader for {log_dir}")

    def _upload_thread() -> None:
        while True:
            try:
                logs_found = list(list_eval_logs(log_dir))
                for log_info in logs_found:
                    log_path = log_info.name
                    # Strip file:// prefix if present
                    if log_path.startswith("file://"):
                        log_path = log_path[7:]  # Remove "file://"
                    if log_path in uploaded_files:
                        continue

                    try:
                        log = read_eval_log(log_path, header_only=True)
                        if log.status not in ["success", "cancelled", "error"]:
                            continue

                        metadata = log.eval.metadata or {}
                        scenario = metadata.get("scenario_name")
                        variation = metadata.get("variation_name")
                        version = metadata.get("version")
                        model = log.eval.model

                        if not all([scenario, variation, version]):
                            print(
                                f"[S3 Uploader] Skipping {Path(log_path).name}: "
                                f"missing metadata (scenario={scenario}, "
                                f"variation={variation}, version={version})"
                            )
                            uploaded_files.add(log_path)  # Don't retry
                            continue

                        # Type narrowing: after the check above, these are all str
                        assert scenario is not None
                        assert variation is not None
                        assert version is not None

                        result = upload_eval(
                            local_path=log_path,
                            scenario=scenario,
                            variation=variation,
                            version=version,
                            model=model,
                            bucket=bucket,
                        )
                        uploaded_files.add(log_path)
                        print(
                            f"[S3 Uploader] Uploaded {Path(log_path).name} "
                            f"to {scenario}/{variation}/{result.version}"
                        )

                    except Exception as e:
                        print(f"[S3 Uploader] Error processing {log_path}: {e}")

            except Exception as e:
                print(f"[S3 Uploader] Error scanning logs: {e}")

            time.sleep(2)

    threading.Thread(target=_upload_thread, daemon=True).start()
