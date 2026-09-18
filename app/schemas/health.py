from pydantic import BaseModel
from typing import Optional, Dict, Any


class HealthResponse(BaseModel):
    status: str
    database: str
    database_name: Optional[str] = None
    database_version: Optional[str] = None
    server_time: Optional[str] = None
    detected_tables_count: Optional[int] = None
    details: Optional[Dict[str, Any]] = None

