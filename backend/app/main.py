import json
from fastapi import FastAPI, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
from shapely.geometry import shape
from . import models, schemas, database
from .utils import compute_overpasses, get_satellite_position, OrbitalPath
from fastapi.middleware.cors import CORSMiddleware
import logging
from geoalchemy2.shape import from_shape
from shapely import wkt
from sqlalchemy.sql import func # Import func
import asyncio
from concurrent.futures import ThreadPoolExecutor

from skyfield.api import EarthSatellite
from .models import Base  # importa o Base do ficheiro models.py na mesma pasta
from .database import engine

executor = ThreadPoolExecutor()  # You can specify max_workers if needed
# Configure the logger
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="Orbital Edge Imaging API")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # frontend URL
    allow_methods=["*"],
    allow_headers=["*"]
)
# Cria todas as tabelas que ainda não existem
Base.metadata.create_all(bind=engine)

@app.post("/tle/upload", response_model=schemas.TLEOut)
async def upload_tle_file(file: UploadFile = File(...), db: Session = Depends(database.get_db)):
    try:
        content = await file.read()
        lines = content.decode("utf-8").splitlines()
        # Expecting TLE format: name, line1, line2
        if len(lines) < 3:
            logger.warning(f"TLE upload failed: Expected 3 non-empty lines, but received {len(lines)}.")
            raise HTTPException(status_code=400,
            detail="TLE file must have at least 3 lines: name, line1, line2")
        name = lines[0].strip()
        line1 = lines[1].strip()
        line2 = lines[2].strip()
        # Validate TLE using Skyfield
        try:
            satellite = EarthSatellite(line1, line2, name=name)
        except ValueError as e:
            logger.error(f"Skyfield TLE validation failed for file '{file.filename}': {e}", exc_info=True)
            raise HTTPException(status_code=400, detail=f"Invalid TLE: {e}")
        # Use NORAD ID as unique identifier
        norad_id = satellite.model.satnum
        # Check if TLE already exists
        existing_tle = db.query(models.TLE).filter(models.TLE.norad_id == norad_id).first()
        if existing_tle:
            # Update existing TLE
            existing_tle.name = name
            existing_tle.line1 = line1
            existing_tle.line2 = line2
            db.commit()
            db.refresh(existing_tle)
            logger.info(f"Updated existing TLE for '{name}' with NORAD ID {norad_id}.")
            return {"norad_id": existing_tle.norad_id, "name": existing_tle.name, "updated": True}
        else:
            # Insert new TLE
            new_tle = models.TLE(name=name, line1=line1, line2=line2, norad_id=norad_id)
            db.add(new_tle)
            db.commit()
            db.refresh(new_tle)
            logger.info(f"Inserted new TLE for '{name}' with NORAD ID {norad_id}.")
            return {"norad_id": new_tle.norad_id, "name": new_tle.name, "updated": False}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during TLE upload: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error.")
    
    
@app.post("/geojson", response_model=schemas.AOIOut)
async def upload_aoi(aoi: schemas.AOICreate, db: Session = Depends(database.get_db)):
    try:
        incoming_geom = shape(aoi.geojson["features"][0]["geometry"])
        
        geom_4326 = from_shape(incoming_geom, srid=4326)
    

        # Use geom_4326 everywhere so SRID matches the DB column (4326)
        existing_aoi = db.query(models.AOI).filter(
            func.ST_Equals(models.AOI.geom, geom_4326)
        ).first()

        if existing_aoi:
            logger.warning(f"An identical AOI already exists. Returning existing ID.")
            return {"id": existing_aoi.id, "name": existing_aoi.name}

        # If no identical AOI exists, create a new one
        new_aoi = models.AOI(name=aoi.name, geom=f'SRID=4326;{incoming_geom.wkt}')
        db.add(new_aoi)
        db.commit()
        db.refresh(new_aoi)
        
        logger.info(f"New AOI '{new_aoi.name}' with ID {new_aoi.id} created.")
        return {"id": new_aoi.id, "name": new_aoi.name}
        
    except Exception as e:
        logger.error(f"Error uploading AOI: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Error processing GeoJSON: {str(e)}")



@app.post("/passes", response_model=list[schemas.PassPredictionOut])
async def compute_passes(request: schemas.PassRequest, db: Session = Depends(database.get_db)):
    logger.info(f"Computing passes for TLE NORAD ID {request.tle_noradid} and AOI ID {request.aoi_id}.")
    tle = db.query(models.TLE).filter(models.TLE.norad_id == request.tle_noradid).first()
    aoi = db.query(models.AOI).filter(models.AOI.id == request.aoi_id).first()
    if not tle:
        logger.warning(f"TLE with NORAD ID {request.tle_noradid} not found.")
        raise HTTPException(status_code=404, detail=f"TLE with NORAD ID {request.tle_noradid} not found.")
    if not aoi:
        logger.warning(f"AOI with ID {request.aoi_id} not found.")
        raise HTTPException(status_code=404, detail=f"AOI with ID {request.aoi_id} not found.")
    print("Sou a duracao no main", request.duration)
    try:
        aoi_geom = wkt.loads(db.scalar(func.ST_AsText(aoi.geom)))
        
        loop = asyncio.get_running_loop()
        passes = await loop.run_in_executor(
            executor,
            compute_overpasses,
            tle.line1,
            tle.line2,
            aoi_geom,
            request.duration,
            request.min_elevation,
            request.daylight_only
        )
        
        saved_passes = []
        for p in passes:
            # Corrected: parse the track_coords list into a JSON string
            track_coords_json = json.dumps(p["track_coords"])
            pp = models.PassPrediction(
                tle_id=tle.norad_id,
                aoi_id=aoi.id,
                start_time=p["start_time"],
                end_time=p["end_time"],
                max_elevation=p["max_elevation"],
                track_coords=track_coords_json
            )
            db.add(pp)
            saved_passes.append(pp) # Keep a reference to the saved object
        
        db.commit()
        
        # Now, return a list of PassPredictionOut schemas
        logger.info(f"Successfully computed and saved {len(saved_passes)} passes.")
        return [
            schemas.PassPredictionOut(
                tle_noradid=p.tle_id,
                aoi_id=p.aoi_id,
                start_time=p.start_time,
                end_time=p.end_time,
                max_elevation=p.max_elevation,
                # Corrected: parse the JSON string from the DB back into a list of floats
                track_coords=json.loads(p.track_coords) 
            ) for p in saved_passes
        ]
    except Exception as e:
        logger.error(f"Error computing passes: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error during pass computation.")

@app.get("/aois", response_model=list[schemas.AOIOut])
async def list_aois(db: Session = Depends(database.get_db)):
    aois = db.query(models.AOI).all()
    logger.info(f"Returning {len(aois)} AOIs.")
    return aois


@app.get("/aois/{aoi_id}", response_model=schemas.AOIGeoJSONOut)
def get_aoi(aoi_id: int, db: Session = Depends(database.get_db)):
    aoi = db.query(models.AOI).filter(models.AOI.id == aoi_id).first()
    if not aoi: raise HTTPException(404, "AOI not found")
    # return geometry as GeoJSON
    geojson = db.execute(func.ST_AsGeoJSON(aoi.geom)).scalar()
    return {"id": aoi.id, "name": aoi.name, "geojson": json.loads(geojson)}

@app.get("/tles", response_model=list[schemas.TLEListOut])
async def list_tles(db: Session = Depends(database.get_db)):
    tles = db.query(models.TLE).all()
    logger.info(f"Returning {len(tles)} TLEs.")
    # Return TLE objects, which will be validated against TLEOut schema
    return tles

@app.get("/track", response_model=schemas.SatellitePositionOut)
async def track_satellite(tle_noradid: int, db: Session = Depends(database.get_db)):
    tle = db.query(models.TLE).filter(models.TLE.norad_id == tle_noradid).first()
    if not tle:
        logger.warning(f"TLE with NORAD ID {tle_noradid} not found.")
        raise HTTPException(status_code=404, detail=f"TLE with NORAD ID {tle_noradid} not found.")
    try:
        logger.info(f"Computing satellite position for NORAD ID {tle_noradid}: {tle.name}")
        position_data = get_satellite_position(tle.line1, tle.line2)
        logger.info(f"Satellite position result: {position_data}")
        return position_data
    except Exception as e:
        logger.exception(f"Error fetching satellite position for NORAD ID {tle_noradid}")
        raise HTTPException(status_code=500, detail=f"Error computing satellite position: {e}")
    
@app.get("/OrbitalPath/{tle_noradid}")
async  def get_orbitalpath(tle_noradid: int, db: Session = Depends(database.get_db)):
    tle = db.query(models.TLE).filter(models.TLE.norad_id == tle_noradid).first()
    if not tle:
        logger.warning(f"TLE with NORAD ID {tle_noradid} not found.")
        raise HTTPException(status_code=404, detail=f"TLE with NORAD ID {tle_noradid} not found.")
    try:
        logger.info(f"Computing orbital path for NORAD ID {tle_noradid}: {tle.name}")
        path_data = await asyncio.to_thread(OrbitalPath, tle.line1, tle.line2)
        return path_data
    except Exception as e:
        logger.exception(f"Error fetching orbital path for NORAD ID {tle_noradid}")
        raise HTTPException(status_code=500, detail=f"Error computing orbital path: {e}")


