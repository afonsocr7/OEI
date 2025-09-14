from sqlalchemy import Column, Float, Integer, String, DateTime, ForeignKey
from geoalchemy2 import Geometry
from .database import Base
from sqlalchemy.orm import relationship

class AOI(Base):
    __tablename__ = "aois"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    geom = Column(Geometry("POLYGON", srid=4326), nullable=False) # Added SRID

class TLE(Base):
    __tablename__ = "tles"
    norad_id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    line1 = Column(String, nullable=False)
    line2 = Column(String, nullable=False)

class PassPrediction(Base):
    __tablename__ = "pass_predictions"
    id = Column(Integer, primary_key=True, index=True)
    tle_id = Column(Integer, ForeignKey('tles.norad_id'), nullable=False) 
    aoi_id = Column(Integer, ForeignKey('aois.id'), nullable=False) 
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    max_elevation = Column(Float)
    track_coords = Column(String)

    tle = relationship("TLE")
    aoi = relationship("AOI") 
    