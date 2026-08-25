"""One-off local setup: creates a "Mielikkix" business account on the LOCAL
dev database and feeds it real Mielikkix content, so the Voice Receptionist
agent (and anything else testing RAG locally) has something real to answer
from -- deliberately separate from the real production business account
(PUBLIC_MIELIKKIX_BUSINESS_ID in website/.env points at app.mielikkix.ai's
live database, which this script never touches).

Ingests two sources:
  1. A crawl of the real public mielikkix.ai site (same pages already
     indexed in production -- homepage, /features, /pricing, /demo).
  2. The supported files in marketing/ (PDF, DOCX, TXT, XLSX). Skips
     .pptx and .mp4 -- the ingestion pipeline has no parser for those
     (see requirements.txt: PyPDF2, python-docx, openpyxl, no pptx/video
     library) -- and skips marketing/temp docs/ (internal dev notes, not
     customer-facing content the agent should ever repeat back).

Usage (server must already be running locally, e.g. on port 8001):
    python scripts/setup_local_mielikkix_business.py [--base-url http://localhost:8001]

Prints the resulting business_id at the end -- put that in .env as
VOICE_AGENT_BUSINESS_ID once this finishes.
"""
import argparse
import sys
import time
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import SessionLocal
from app.models.business import Business

REPO_ROOT = Path(__file__).resolve().parents[3]
MARKETING_DIR = REPO_ROOT / "marketing"
SUPPORTED_FILES = [
    "Mielikkix-AI-About.docx",
    "Mielikkix-AI-FAQ.pdf",
    "Mielikkix-AI-Getting-Started.txt",
    "Mielikkix-AI-Pricing-Comparison.xlsx",
]


def _bump_plan_to_unlimited(business_id: str) -> None:
    """Free plan caps document uploads at 2 (see app/core/plans.py) -- this
    business needs to hold the crawled pages + the 4 marketing files at
    once, so it's bumped directly in the DB the same way tests do (no
    self-serve or admin-auth path needed for a local dev-only business)."""
    db = SessionLocal()
    try:
        biz = db.query(Business).filter(Business.id == business_id).first()
        biz.plan = "business"
        biz.status = "active"
        db.commit()
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8001")
    args = parser.parse_args()

    unique = uuid.uuid4().hex[:8]
    # example.com, not .local/.test -- pydantic's email-validator rejects
    # reserved special-use TLDs even for local-only accounts like this one.
    email = f"dev-mielikkix-{unique}@example.com"

    with httpx.Client(base_url=args.base_url, timeout=60.0) as client:
        print(f"Registering local business against {args.base_url} ...")
        resp = client.post(
            "/api/auth/register",
            json={
                "business_name": "Mielikkix",
                "business_slug": f"mielikkix-local-{unique}",
                "industry": "technology",
                "full_name": "Local Dev Admin",
                "email": email,
                "password": "local-dev-password-123",
            },
        )
        resp.raise_for_status()
        user = resp.json()
        business_id = user["business_id"]
        token = resp.cookies.get("access_token")
        headers = {"Authorization": f"Bearer {token}"}
        print(f"  business_id = {business_id}")

        _bump_plan_to_unlimited(business_id)
        print("  plan bumped to unlimited document uploads (local dev only)")

        print("Queuing a crawl of the real public mielikkix.ai site ...")
        resp = client.post(
            "/api/documents/from-website",
            json={"url": "https://mielikkix.ai"},
            headers=headers,
        )
        if resp.status_code == 200:
            print(f"  {resp.json()['message']}")
        else:
            print(f"  crawl request failed ({resp.status_code}): {resp.text}")

        print("Uploading marketing/ documents ...")
        for filename in SUPPORTED_FILES:
            path = MARKETING_DIR / filename
            if not path.is_file():
                print(f"  skipping {filename} (not found at {path})")
                continue
            with path.open("rb") as f:
                resp = client.post(
                    "/api/documents",
                    files={"file": (filename, f)},
                    headers=headers,
                )
            if resp.status_code == 200:
                print(f"  uploaded {filename}")
            else:
                print(f"  failed to upload {filename} ({resp.status_code}): {resp.text}")

        print(
            "\nDocuments are processed in the background (embedding takes a "
            "few seconds each) -- check progress with:\n"
            f'  curl -s -H "Authorization: Bearer {token}" {args.base_url}/api/documents | python -m json.tool'
        )
        print(f"\nDONE. business_id = {business_id}")
        print("Add this to .env as VOICE_AGENT_BUSINESS_ID.")


if __name__ == "__main__":
    main()
