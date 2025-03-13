# Overview
This repo contains guidance and scripts to assist with syncing content from one GitHub repo to another -- both git content and GitHub content. I started working on this when trying to move my team from a repo on the public GitHub instance to GHEC EMU. Unfortunately, while working on getting our GHEC EMU repo up and running, the import feature broke and as of this date is still broken. And in the intervening months, many changes had been made in our source repo, so I was looking at ways that I could update our initial import into GHEC EMU with all the changes that had been made during those months. In the end I decided that that wasn't worthwhile, and instead I'll wait for the import feature to be fixed. I'm publishing this repo in the hopes that some of it will be useful to another team and save you some time.

# Usage
The examples below reference two fake repositories (source-org/source-repo and dest-org/dest-repo) for convenience rather than constantly referring to "the source repo" and "the dest repo". Replace these with your actual source and destination.

## Commits

### Preparation
Before updating any branches as described below, setup `source-org/source-repo` as a remote in either your fork of `dest-org/dest-repo` (if you want to send a PR) or in a clone of `dest-org/dest-repo` itself (if you want to push directly).

```text
git remote add source-repo https://github.com/source-org/source-repo.git
```

### Updating main branch via a PR

```text
git checkout main
git pull
git checkout -b mergeFromSource

git remote update
git merge source-repo/main

git push -u origin HEAD
Create a PR
```

### Updating branches via a direct push

```text
git remote update
git checkout -b myBranch source-repo/myBranch
git push -u origin HEAD
```

## Wiki
Same as importing commits into `main` as described above, but add a `.wiki` suffix to the names of the source and destination repos when cloning (ex. `https://github.com/source-org/source-repo.wiki.git`). Also note that wikis use `master` as their primary branch rather than `main`. And I don't think there's a way to respond to PRs on the wiki repo, so I've just been pushing the changes directly to `master`.

## GitHub Releases & Assets

Importing releases will also import the corresponding tags and those tags will reference the same commit SHAs that they do in the source repo, so before importing releases, ensure that the corresponding commits are already present in the destination repo.

```text
python releases\sync-releases.py --source-repo source-org/source-repo --dest-repo dest-org/dest-repo --source-token <PAT for source repo> --dest-token <PAT for dest repo>
```

## GitHub Issues & PRs

The `issues/sync-issues.py` script is not working. There's a partial implementation, but I don't believe there is a way to import issues and PRs (especially PRs) at high fidelity using [the public REST APIs](https://docs.github.com/en/rest). One problem is that when [adding comments to an issue or PR](https://docs.github.com/en/rest/issues/comments?apiVersion=2022-11-28#create-an-issue-comment), there's no way to specify the date or author, just the body. So the comment will be shown as having been created by whichever GitHub user created your PAT and created at the time that the script was run. This is perhaps not the end of the world, since you could add a header on each comment providing the real author and creation date. However, when [creating PRs](https://docs.github.com/en/rest/pulls/pulls?apiVersion=2022-11-28#create-a-pull-request), I struggled to find an appropriate way to provide the `head` commitish. The problem is that the original source branch may not exist anymore and the source commit SHA may not be present in the source repo, if it came from a fork. So I wasn't able to get a high-fidelity copy of the PRs as you would get from using GitHub's repo import process. But if you have ideas on how to solve that, or perhaps don't care about achieving such high-fidelity, perhaps this will serve as a starting point for you.

Note that one of the biggest issues with creating a high-fidelity copy of issues and PRs is that when creating them you are not able to specify their number (ex. the value 10076 in https://github.com/microsoft/pyright/issues/10076). I wanted the issues and PRs in our destination repo to have the same numbers as they originally had in the source repo, so any links to source repo issues and PRs in our wiki, issue content, comments, etc would be easily mapped to their location in the destination repo by simply updating the organization and repo names -- the number would always be the same. So that means that when importing issues you need to do them in order starting from 1. But, issues and PRs (and discussions?) use the same namespace for their numbers, which means that if you create any issues/PRs/discussions in your destination repo before importing from your source repo, you may find yourself in a situation where number X in the source repo is an issue, but in the destination repo X is a PR (or vice versa).