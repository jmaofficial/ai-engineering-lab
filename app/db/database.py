from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import os

load_dotenv()
db_url = os.getenv("DATABASE_URL")
if not db_url:
    raise ValueError("DATABSE URL NOT FOUND IN ENVIRONMENT FILE")
engine = create_engine(db_url)

SessionLocal = sessionmaker(bind=engine)
