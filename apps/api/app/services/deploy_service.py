"""MielikkiX Admin -> Articles: publish-to-live pipeline, the last mile of

    Admin -> VPS Postgres (source of truth) -> Astro build -> Hostinger

No job queue exists in this codebase (see seo_audit_service.py's own
docstring for the same note) -- this runs as a FastAPI BackgroundTasks
callback, the same shape run_audit already uses, opening its OWN DB
session since the request's session is closed by the time this runs.

Nothing here is a stub or a fake success. If WEBSITE_REPO_PATH or the
Hostinger SFTP settings are unset, `run_deploy` returns a real failure with
a clear, honest reason -- it does NOT mark the article "live". As of this
feature's implementation, none of these were configured anywhere in this
repo (confirmed by inspecting infra/deploy/README.md, .github/workflows/
ci.yml, and the full repo for any existing FTP/SFTP/SSH mechanism -- there
is none), so a fresh deploy of this feature will report "failed" honestly
until an operator fills in the real values. See core/config.py's own
comments on each setting for exactly what's needed and where to get it.

Security: no shell command is ever built from user/admin input -- `npm run
build` runs with a fixed argv (no shell=True, no string interpolation of
anything admin-controlled), and the SFTP step uploads a fixed local
directory (website/dist) to a fixed configured remote path. There is no
route or parameter anywhere that lets a caller (even an authenticated
platform admin) submit an arbitrary command or path.
"""
import os
import stat
import subprocess
from dataclasses import dataclass

from ..core.config import settings
from ..core.database import SessionLocal
from . import article_service


@dataclass
class DeployResult:
    success: bool
    message: str


def _missing_config() -> list[str]:
    missing = []
    if not settings.website_repo_path:
        missing.append("WEBSITE_REPO_PATH")
    if not settings.website_deploy_sftp_host:
        missing.append("WEBSITE_DEPLOY_SFTP_HOST")
    if not settings.website_deploy_sftp_username:
        missing.append("WEBSITE_DEPLOY_SFTP_USERNAME")
    if not settings.website_deploy_sftp_password:
        missing.append("WEBSITE_DEPLOY_SFTP_PASSWORD")
    if not settings.website_deploy_remote_path:
        missing.append("WEBSITE_DEPLOY_REMOTE_PATH")
    return missing


def _build_website() -> DeployResult:
    website_dir = os.path.join(settings.website_repo_path, "website")
    if not os.path.isdir(website_dir):
        return DeployResult(False, f"Expected a website/ directory at {website_dir!r} but it doesn't exist.")

    try:
        subprocess.run(
            ["npm", "run", "build"],
            cwd=website_dir,
            check=True,
            capture_output=True,
            text=True,
            timeout=600,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        return DeployResult(False, "Website build timed out after 10 minutes.")
    except subprocess.CalledProcessError as exc:
        # stderr from a failed `npm run build` is safe to surface (build
        # tool output, never a secret -- no credential is ever passed as a
        # build argument or env var read by the Astro build itself).
        tail = (exc.stderr or "")[-2000:]
        return DeployResult(False, f"Website build failed: {tail}")

    dist_dir = os.path.join(website_dir, "dist")
    if not os.path.isdir(dist_dir):
        return DeployResult(False, "Website build completed but produced no dist/ directory.")
    return DeployResult(True, dist_dir)


def _upload_via_sftp(local_dist_dir: str) -> DeployResult:
    import paramiko

    try:
        transport = paramiko.Transport((settings.website_deploy_sftp_host, settings.website_deploy_sftp_port))
        transport.connect(
            username=settings.website_deploy_sftp_username,
            password=settings.website_deploy_sftp_password,
        )
        sftp = paramiko.SFTPClient.from_transport(transport)
    except Exception as exc:
        return DeployResult(False, f"Could not connect to the deploy target: {exc.__class__.__name__}")

    try:
        remote_root = settings.website_deploy_remote_path.rstrip("/")

        def _ensure_remote_dir(path: str) -> None:
            parts = path.strip("/").split("/")
            current = ""
            for part in parts:
                current = f"{current}/{part}" if current else f"/{part}"
                try:
                    sftp.stat(current)
                except FileNotFoundError:
                    sftp.mkdir(current)

        for root, _dirs, files in os.walk(local_dist_dir):
            rel_root = os.path.relpath(root, local_dist_dir)
            remote_dir = remote_root if rel_root == "." else f"{remote_root}/{rel_root.replace(os.sep, '/')}"
            _ensure_remote_dir(remote_dir)
            for filename in files:
                local_path = os.path.join(root, filename)
                remote_path = f"{remote_dir}/{filename}"
                sftp.put(local_path, remote_path)
    except Exception as exc:
        return DeployResult(False, f"Upload to the deploy target failed partway through: {exc.__class__.__name__}")
    finally:
        try:
            sftp.close()
            transport.close()
        except Exception:
            pass

    return DeployResult(True, "Uploaded successfully.")


def run_deploy(article_id: str) -> None:
    """Entry point for BackgroundTasks -- see app/api/admin_articles.py's
    publish/unpublish routes. Opens its own DB session; never raises back
    to the caller (the HTTP response has already been sent by the time
    this runs)."""
    db = SessionLocal()
    try:
        missing = _missing_config()
        if missing:
            article_service.record_deployment_result(
                db,
                article_id,
                success=False,
                message=(
                    "Automatic deployment isn't configured on this server yet. "
                    f"Missing: {', '.join(missing)}. The article is saved in the "
                    "database, but the public website hasn't been rebuilt."
                ),
            )
            return

        build_result = _build_website()
        if not build_result.success:
            article_service.record_deployment_result(db, article_id, success=False, message=build_result.message)
            return

        upload_result = _upload_via_sftp(build_result.message)
        article_service.record_deployment_result(
            db, article_id, success=upload_result.success, message=upload_result.message
        )
    finally:
        db.close()
