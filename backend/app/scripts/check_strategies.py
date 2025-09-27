# app/scripts/check_strategies.py
from sqlalchemy.orm import Session
from app.db import engine
from app.models import Strategy

def main():
    with Session(engine) as session:
        rows = session.query(Strategy).limit(10).all()
        for r in rows:
            print(f"{r.id} | {r.label} | moods={r.moods} | source={r.source_name}")

if __name__ == "__main__":
    main()
