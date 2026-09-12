from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="MedSync CATMS API",
    description="Clinic Appointment and Treatment Management System API",
    version="0.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"message": "MedSync CATMS API is running"}


@app.get("/health")
def health():
    return {"status": "healthy"}
