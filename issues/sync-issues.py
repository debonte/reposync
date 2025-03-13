import sys
import logging
import argparse
from typing import Optional, Union
import github3
from github3.repos.repo import Repository
from github3.issues.issue import Issue
from github3.pulls import PullRequest

parser = argparse.ArgumentParser(description="Migrate GitHub Releases from a private repo to a GHEC EMU instance.")
parser.add_argument("--source-repo", required=True, help="Source GitHub repo (format: owner/repo)")
parser.add_argument("--dest-repo", required=True, help="Destination GitHub repo (format: owner/repo)")
parser.add_argument("--source-token", required=True, help="GitHub PAT for source repo")
parser.add_argument("--dest-token", required=True, help="GitHub PAT for destination repo")
parser.add_argument("--log-file", default="migration.log", help="Log file path (default: migration.log)")
parser.add_argument("--max-threads", type=int, default=5, help="Number of concurrent threads for uploads/downloads (default: 5)")
parser.add_argument("--dry-run", action="store_true", help="Enable dry-run mode (no actual changes)")

args = parser.parse_args()

# Setup logging
logging.basicConfig(
    filename=args.log_file,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))

TEMP_DOWNLOAD_DIR = "release_assets"


def get_issue_or_pr(repo: Repository, number: int) -> Optional[Union[Issue, PullRequest]]:
    try:
        pr = repo.pull_request(number)
        if pr:
            return pr
    except Exception:
        pass

    try:
        issue = repo.issue(number)
        if issue:
            return issue
    except Exception:
        pass

    return None


def create_issue(dest_repo: Repository, source_issue: Issue) -> Optional[Issue]:
    try:
        labels = [label for label in source_issue.labels()]

        issue = dest_repo.create_issue(
            title=source_issue.title,
            body=source_issue.body or '',
            labels=labels or None
        )

        assert issue, f"Failed to create issue #{source_issue.number} in destination repo"

        # Add comments
        for source_comment in source_issue.comments():
            header = f"Originally written by {source_comment.user.login} on {source_comment.created_at.isoformat()} at {source_comment.url}"
            issue.create_comment(body=header + "\n\n" + source_comment.body)
        
        # Update issue state if closed
        if source_issue.state == 'closed':
            issue.close()
    
        return issue
    except Exception as e:
        print(f"Error creating issue #{source_issue.number}: {e}")
        return None

def create_pr(dest_repo: Repository, source_pr: PullRequest) -> Optional[PullRequest]:
    try:
        # dest_repo.create_branch_ref(name=f"migrate_pr_{source_pr.number}", sha=source_pr.head.sha)

        # What to pass for the head? When looking at my source repo, I found examples where the source PR's
        # head was not a fork branch, but the branch was regularly deleted and recreated, so even if it does
        # exist, we wouldn't want to use the existing branch here. We could also use the head commit SHA from
        # the source PR, but in the case of PRs from forks, that commit may not exist in the source repo.

        pr = dest_repo.create_pull(
            title=source_pr.title,
            base=source_pr.base.ref,
            head=source_pr.head.sha,
            body=source_pr.body or ''
        )
        
        assert pr, f"Failed to create PR #{source_pr.number} in destination repo"

        # Add comments
        for source_comment in source_pr.issue_comments():
            header = f"Originally written by {source_comment.user.login} on {source_comment.created_at.isoformat()} at {source_comment.url}"
            pr.create_comment(body=header + "\n\n" + source_comment.body)

        # Add review comments
        for source_review_comment in source_pr.review_comments():
            header = f"Originally written by {source_review_comment.user.login} on {source_review_comment.created_at.isoformat()} at {source_review_comment.url}"
            pr.create_review_comment(body=header + "\n\n" + source_review_comment.body,
                                     commit_id=source_review_comment.commit_id,
                                     path=source_review_comment.path,
                                     position=source_review_comment.position)

        # Update PR state if closed
        if source_pr.state == 'closed':
            pr.close()

        return pr
    except Exception as e:
        print(f"Error creating PR #{source_pr.number}: {e}")
        return None


def migrate_labels(source_repo: Repository, dest_repo: Repository):
    try:
        source_labels = source_repo.labels()
        for label in source_labels:
            try:
                dest_repo.label(label.name)
            except github3.exceptions.NotFoundError:
                dest_repo.create_label(label.name, label.color)
    except Exception as e:
        assert False, f"Error migrating labels: {e}"


def migrate_issues(max_number: Optional[int] = None):
    source_gh = github3.GitHub("https://github.com/{args.source_repo}", token=args.source_token)
    source_components = args.source_repo.split("/")
    source_repo = source_gh.repository(source_components[0], source_components[1])
    if not source_repo:
        logging.error(f"❌ Source repository {args.source_repo} not found.")
        return

    dest_gh = github3.GitHub("https://github.com/{args.dest_repo}", token=args.dest_token)
    dest_components = args.dest_repo.split("/")
    dest_repo = dest_gh.repository(dest_components[0], dest_components[1])
    if not dest_repo:
        logging.error(f"❌ Destination repository {args.dest_repo} not found.")
        return

    migrate_labels(source_repo, dest_repo)

    # Get all issues/PRs from source repo
    source_issue_and_pr_numbers = [issue.number for issue in source_repo.issues(state='all')]
    next_source_number = max(source_issue_and_pr_numbers) + 1 if source_issue_and_pr_numbers else 1

    logging.info(f"Syncing issues/PRs from {source_repo} to {dest_repo}")
    logging.info(f"Processing numbers 1 through {max_number}")

    # Turn down github3 logging verobosity
    logging.getLogger('github3').setLevel(logging.CRITICAL)

    # Process each number in sequence to ensure we handle both issues and PRs
    for number in range(1, next_source_number):
        # Get source item (issue or PR)
        source_item = get_issue_or_pr(source_repo, number)
        if not source_item:
            print(f"#{number}: Not found in source repo - skipping")
            continue

        if source_item.number != number:
            print(f"#{number}: Number mismatch: {source_item.number} != {number} -- {source_item.url}")
            continue
            
        # Check if item exists in destination repo
        dest_item = get_issue_or_pr(dest_repo, number)

        if isinstance(source_item, PullRequest):
            # Handle PR (as issue with placeholder)
            if dest_item:
                # PR number exists in destination - update if it's a placeholder issue
                if isinstance(dest_item, PullRequest):
                    if source_item.title == dest_item.title:
                        print(f"#{number}: PR exists in destination - skipping")
                    else:
                        print(f"#{number}: WARNING: PR title mismatch - skipping")
                elif isinstance(dest_item, Issue):
                    print(f"#{number}: WARNING: Source is PR, destination is issue - skipping")
                else:
                    assert False, f"Unknown type for destination item #{number}: {type(dest_item)}"
            else:
                print(f"#{number}: Creating PR")
                placeholder = create_pr(dest_repo, source_item)
                assert placeholder, f"Failed to create placeholder PR for #{number}"
                assert placeholder.number == number, f"Placeholder PR number mismatch: {placeholder.number} != {number}"
        elif isinstance(source_item, Issue):
            if dest_item:
                if isinstance(dest_item, Issue):
                    if source_item.title == dest_item.title:
                        print(f"#{number}: Issue exists in destination - skipping")
                    else:
                        print(f"#{number}: WARNING: Issue title mismatch - skipping")
                elif isinstance(dest_item, PullRequest):
                    print(f"#{number}: WARNING: Source is issue, destination is PR - skipping")
                else:
                    assert False, f"Unknown type for destination item #{number}: {type(dest_item)}"
            else:
                print(f"#{number}: Creating new issue")
                issue = create_issue(dest_repo, source_item)
                assert issue, f"Failed to create issue for #{number}"
                assert issue.number == number, f"Issue number mismatch: {issue.number} != {number}"
        else:
            assert False, f"Unknown type for source item #{number}: {type(source_item)}"


if __name__ == "__main__":
    migrate_issues()
