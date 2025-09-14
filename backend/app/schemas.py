from pydantic import BaseModel, root_validator
from typing import List, Optional, Any
import json

class AOICreate(BaseModel):
    name: str
    geojson: dict

class PassRequest(BaseModel):
    tle_noradid: int
    aoi_id: int
    daylight_only: bool = False
    min_elevation: Optional[float] = 5.0
    duration: Optional[int] = 24 

# --- Output schemas ---
class AOIOut(BaseModel):
    id: int
    name: str

    class Config:
        orm_mode = True

class AOIGeoJSONOut(AOIOut):
    geojson: dict

class TLEOut(BaseModel):
    norad_id: int
    name: str
    updated: bool

    class Config:
        orm_mode = True

class TLEListOut(BaseModel):
    norad_id: int
    name: str
    line1: str
    line2: str

    class Config:
        orm_mode = True

class PassPredictionOut(BaseModel):
    tle_noradid: int
    aoi_id: int
    start_time: Any # Use Any for Datetime to let Pydantic handle it
    end_time: Any
    max_elevation: float
    track_coords: List[List[float]]

    class Config:
        orm_mode = True

class SatellitePositionOut(BaseModel):
    latitude: float
    longitude: float
    altitude_m: float
    fov_radius_m: float
