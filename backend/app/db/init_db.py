import asyncio
from backend.app.db.base import engine, Base
from backend.app.models.models import AnalysisRequest, Trend, Source

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

if __name__ == "__main__":
    asyncio.run(init_db())
