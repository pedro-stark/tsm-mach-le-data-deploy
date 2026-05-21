from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from dotenv import load_dotenv
import os

from routers.version import router as version_router
from routers.recommendation import router as recommendation_router
from routers.enum import router as enum_router
import models.user  # noqa: F401 — registers Users with SQLAlchemy's class registry

# load env variables
load_dotenv()

swagger_ui_parameters = {"syntaxHighlight": {"theme": os.getenv("SWAGGER_THEME")}}
description: str = """
Project for module: TSM_MachLeData (ML Ops)
This FastAPI serves as:
- Backend for the Streamlit GUI
- Standalone RestAPI service
"""

# setup app
app = FastAPI(
    title=os.getenv("TITLE"),
    description=description,
    summary="Cinematch API: Project for TSM_MachLeData",
    version=os.getenv("VERSION_NR"),
    swagger_ui_parameters=swagger_ui_parameters,
)

# add routers (this could be optimized but is sufficient for two routers)
app.include_router(version_router, prefix="/api", tags=["version"])
app.include_router(
    recommendation_router, prefix="/api/recommendation", tags=["recommendation"]
)
app.include_router(enum_router, prefix="/api/enum", tags=["enums"])


# setup cors
origins: list = [
    "*", # allow all ports, so that the api can be used as a webservice
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
