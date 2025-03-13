import sys
import os
import logging
import argparse
import github3

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

def create_release(dest_repo, source_release):
    if args.dry_run:
        logging.info(f"[DRY-RUN] Would create release: {source_release.name}")
        return {"upload_url": "mock_url"}  # Simulated upload URL

    return dest_repo.create_release(tag_name=source_release.tag_name,
                                    target_commitish=source_release.target_commitish,
                                    name=source_release.name,
                                    body=source_release.body or "",
                                    draft=source_release.draft,
                                    prerelease=source_release.prerelease)


def download_asset(asset):
    if args.dry_run:
        logging.info(f"[DRY-RUN] Would download asset: {asset.name}")
        return f"mock_path/{asset.name}"
    
    logging.info(f"Downloading asset: {asset.name} (size: {asset.size} bytes)")

    download_dir = os.path.join(TEMP_DOWNLOAD_DIR, str(asset.id))
    os.makedirs(download_dir, exist_ok=True)
    local_path = os.path.join(download_dir, asset.name)

    asset.download(local_path)

    logging.info(f"✅ Downloaded asset: {asset.name}")
    return local_path


def get_content_type(file_name):
    """Get the content type based on the file extension"""
    _, ext = os.path.splitext(file_name)
    if ext == ".zip" or ext == ".vsix":
        return "application/zip"
    elif ext == ".tgz":
        return "application/gzip"
    elif ext == ".json":
        return "application/json"
    elif ext == ".manifest":
        return "application/manifest+json"
    elif ext == ".p7s":
        return "application/pkcs7-signature"
    else:
        return "application/octet-stream"


def upload_asset(target_release, file_path):
    """Upload the specified file as an asset attached to the specified release."""
    if args.dry_run:
        logging.info(f"[DRY-RUN] Would upload asset: {file_path}")
        return

    logging.info(f"Uploading asset: {file_path}")

    file_name = os.path.basename(file_path)

    with open(file_path, 'rb') as file_obj:
        target_release.upload_asset(content_type=get_content_type(file_name), name=file_name, asset=file_obj)

    logging.info(f"✅ Uploaded asset: {file_name}")


def migrate_releases():
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

    release_names_in_destination_repo = [release.name for release in dest_repo.releases()]
    releases_in_source_repo = list(source_repo.releases())

    for source_release in releases_in_source_repo:
        logging.info(f"🚀 Processing release: {source_release.name}")

        if source_release.name in release_names_in_destination_repo:
            logging.info(f"⏭️ Skipping existing release: {source_release.name}")
            continue

        new_release = create_release(dest_repo, source_release)
        if not new_release:
            logging.error(f"❌ Failed to create release {source_release.name} in destination repo.")
            continue

        # Asset download/upload is intentionally not parallelized to avoid hitting GitHub API rate limits
        source_assets = list(source_release.assets())
        downloaded_files = [download_asset(asset) for asset in source_assets]
        logging.info(f"All assets for release {source_release.name} downloaded.")

        for file_path in downloaded_files:
            upload_asset(new_release, file_path)

        logging.info(f"All assets for release {source_release.name} uploaded.")

if __name__ == "__main__":
    migrate_releases()
