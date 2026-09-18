# src/database.py
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Numeric, DateTime, JSON, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from src.config import settings

engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class JobModel(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String, unique=True, index=True)
    platform = Column(String)
    title = Column(String)
    company = Column(String)
    contract_type = Column(String)
    location = Column(String)
    description_url = Column(Text)
    raw_description = Column(Text)
    status = Column(String, default="NEW") # NEW, ANALYZED, CV_READY, PENDING_APPROVAL, APPLIED, REJECTED
    created_at = Column(DateTime, default=datetime.utcnow)

class ApplicationModel(Base):
    __tablename__ = "applications"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, index=True)
    ats_score = Column(Numeric)
    missing_skills = Column(JSON)
    tailored_cv_path = Column(String)
    audit_trail = Column(JSON, default=[])
    applied_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

def init_db():
    Base.metadata.create_all(bind=engine)