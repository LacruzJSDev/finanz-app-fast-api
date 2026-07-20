## Setup
1. `python3 -m venv venv && source venv/bin/activate`
2. `pip install -r requirements.txt`
3. `cp .env.example .env`
4. `docker compose up -d`
5. `uvicorn app.main:app --reload`