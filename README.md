# CATMS-Backend

Python FastAPI REST API backend and PostgreSQL database scripts for **MedSync / CATMS**.

## Technical Stack

- **Language & Runtime**: Python 3.11+
- **Framework**: FastAPI (`uvicorn` ASGI server)
- **Database Engine**: PostgreSQL 16+ (Hosted on Neon Cloud / local PostgreSQL)
- **Data Access**: `asyncpg` / `psycopg2`
- **Containerization**: Docker & Docker Compose

## Repository Structure

```text
CATMS-Backend/
├── app/             # FastAPI application
│   ├── __init__.py
│   └── main.py      # Entry point & base routes
├── database/        # 10-step sequential SQL scripts pipeline (01 to 10)
├── compose.yaml     # Multi-container Docker Compose setup
├── Dockerfile       # Container build definition
├── requirements.txt # Python dependencies
└── .env.example     # Environment configuration template
```

## Local Development Execution

### Option 1: Local Python Environment

1. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On Linux/macOS:
   source venv/bin/activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Setup environment variables:
   ```bash
   cp .env.example .env
   ```

4. Run FastAPI development server with hot-reload:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```

The API will be available at `http://localhost:8000` (interactive documentation at `http://localhost:8000/docs`).

### Option 2: Docker Compose

```bash
docker compose up --build
```

## Central Documentation

For system specifications and architecture guidelines, visit the **[project-docs Repository](https://github.com/datanexus-cs3043/project-docs)**.
