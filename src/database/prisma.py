from prisma import Prisma

prisma = Prisma()

async def get_prisma():
    await prisma.connect()
    try:
        yield prisma
    finally:
        await prisma.disconnect() 