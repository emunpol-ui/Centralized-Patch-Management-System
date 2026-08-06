# Centralized Patch Management System (CPMS)

Windows-only centralized patch management prototype (OJT/Capstone project).

> Full installation, deployment, and user guides are produced under ticket
> **TEST-002 - Final Documentation & Demo Preparation**. This file currently
> covers only what is needed to run the backend foundation established in
> **CORE-001**.

## Quick Start (Backend Foundation)

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment variables
cp .env.example .env             # Windows: copy .env.example .env

# 4. Run the server
python run.py
```

Then open:

- Swagger UI: <http://localhost:8000/docs>
- ReDoc: <http://localhost:8000/redoc>
- Health check: <http://localhost:8000/api/health>

## Project Structure

See the Software Architecture Document (`docs/`) for the complete,
authoritative project structure. The high-level layout is:

```
CPMS/
├── backend/     # FastAPI application (see backend/ for internal layers)
├── agent/       # Windows Client Agent (implemented starting CLIENT-*)
├── repository/  # Approved installer storage (implemented starting REP-*)
├── logs/        # Application log output
├── scripts/     # Operational/maintenance scripts
├── tests/       # Automated tests (implemented starting TEST-*)
├── docs/        # Project documentation
├── requirements.txt
├── run.py
└── .env
```
