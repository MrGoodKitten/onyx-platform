import asyncio
from onyx_engine.core_omega import ONYXOmegaCore

if __name__=='__main__':
    engine=ONYXOmegaCore(workers=8)
    asyncio.run(engine.run())
