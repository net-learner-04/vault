from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from db import Base, engine, SessionLocal, run_migrations
from users import router as user_router
from users import create_admin_if_not_exists, check_dormant_accounts, clean_old_trash
from files import router as file_router
from admin import router as admin_router

Base.metadata.create_all(bind=engine)
run_migrations()

app = FastAPI(title="Vault")

app.include_router(user_router)
app.include_router(file_router)
app.include_router(admin_router)

app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")


@app.on_event("startup")
def startup():
    db = SessionLocal()
    try:
        create_admin_if_not_exists(db)
        check_dormant_accounts(db)
        clean_old_trash(db)
    finally:
        db.close()
