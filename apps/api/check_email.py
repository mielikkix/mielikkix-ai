import asyncio
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.models.business import BusinessSettings

BUSINESS_ID = "45d99157-e525-4164-bd32-339c2206df9d"

async def main():
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(BusinessSettings).where(
                BusinessSettings.business_id == BUSINESS_ID
            )
        )
        settings = result.scalar_one_or_none()

        if settings:
            print("CONTACT EMAIL:", settings.contact_email)
        else:
            print("NO BUSINESS SETTINGS FOUND")

asyncio.run(main())
