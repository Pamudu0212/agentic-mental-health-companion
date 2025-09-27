# app/seed_strategies.py
from __future__ import annotations
import csv
from pathlib import Path
from sqlalchemy.orm import Session
from .db import engine, Base
from .models import Strategy

Base.metadata.create_all(bind=engine)

CSV_PATH = Path(__file__).resolve().parent / "data" / "mh_strategies_seed.csv"

def seed_from_csv() -> None:
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"Seed CSV not found at {CSV_PATH}")

    with CSV_PATH.open("r", encoding="utf-8") as f, Session(engine) as session:
        reader = csv.DictReader(f)
        inserted = updated = 0
        for row in reader:
            # Normalize/convert types
            row["time_cost_sec"] = int(row.get("time_cost_sec") or 0)

            s = session.get(Strategy, row["id"])
            if s:
                for k, v in row.items():
                    setattr(s, k, v)
                updated += 1
            else:
                session.add(Strategy(**row))
                inserted += 1
        session.commit()
        print(f"✅ Seed complete. Inserted {inserted}, updated {updated}.")

if __name__ == "__main__":
    seed_from_csv()
