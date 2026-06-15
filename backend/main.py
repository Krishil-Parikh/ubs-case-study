from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.api.routes import pipeline, health

app = FastAPI(title="ERS Evidence Pipeline API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(pipeline.router)
