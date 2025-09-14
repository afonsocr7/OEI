from skyfield.api import EarthSatellite, load, wgs84
from shapely.geometry import Point, shape
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone 
from skyfield.api import EarthSatellite
from fastapi import HTTPException
from skyfield.api import utc
from shapely.geometry import Point
from shapely.ops import unary_union
import numpy as np
from math import sqrt, pi
from skyfield.api import EarthSatellite, load, wgs84
from datetime import datetime, timedelta, timezone
import math
from skyfield.api import EarthSatellite, wgs84, load
from skyfield import almanac
from shapely.geometry import Point
from datetime import datetime, timedelta, timezone
import dateutil.parser
import numpy as np
ts = load.timescale()
ephem = load('de421.bsp')  # planetary ephemeris for sun/moon positions
sun = ephem['Sun']

def compute_overpasses(tle_line1, tle_line2, aoi_geom, duration_hours, min_elevation_degrees=5, daylight_only=False):
    satellite = EarthSatellite(tle_line1, tle_line2, 'satellite', ts)
    centroid = aoi_geom.centroid
    print("AOI centroid:", centroid)
    observer = wgs84.latlon(latitude_degrees=centroid.y, longitude_degrees=centroid.x)

    now = datetime.now(timezone.utc)
    print("Duration hours:", duration_hours)
    end_time = now + timedelta(hours=duration_hours)
    t0 = ts.utc(now)
    t1 = ts.utc(end_time)

    # find rise / culminate / set events for the observer
    times, events = satellite.find_events(observer, t0, t1, altitude_degrees=min_elevation_degrees)

    passes = []
    current_pass = {}

    for time, event in zip(times, events):
        if event == 0:  # rise
            current_pass = {"start_time": time, "end_time": None, "max_elevation": None}
        elif event == 1:  # culminate
            current_pass["culminate_time"] = time
            alt, _, _ = (satellite - observer).at(time).altaz()
            current_pass["max_elevation"] = float(alt.degrees)
        elif event == 2:  # set
            # ensure we had a start
            if "start_time" in current_pass and current_pass["start_time"] is not None:
                current_pass["end_time"] = time

                # --- IMPORTANT: pass Skyfield Time objects directly to ts.linspace ---
                times_in_pass_ts_full = ts.linspace(current_pass["start_time"], current_pass["end_time"], 1000)

                # optional daylight-only filtering
                if daylight_only:
                    # dark_twilight_day(ephemeris, topos) returns a function of times
                    get_sky_state = almanac.dark_twilight_day(ephem, observer)
                    sky_state_array = get_sky_state(times_in_pass_ts_full)
                    # according to skyfield, value 4 == day. Keep this as you used before.
                    sun_is_up_mask = (sky_state_array >= 3)

                    # if no part of the pass occurs during day, skip it
                    if not np.any(sun_is_up_mask):
                        current_pass = {}
                        continue

                    # narrow the pass to daylight times
                    daylight_times = times_in_pass_ts_full[sun_is_up_mask]
                    # replace start/end for computing track
                    times_in_pass_ts_full = daylight_times
                    current_pass["start_time"] = daylight_times[0]
                    current_pass["end_time"] = daylight_times[-1]

                # compute geocentric positions for the pass sample times
                geocentric_in_pass = satellite.at(times_in_pass_ts_full)
                subpoints_in_pass = wgs84.subpoint(geocentric_in_pass)
                lats_in_pass = subpoints_in_pass.latitude.degrees
                lons_in_pass = subpoints_in_pass.longitude.degrees

                # keep only points that are inside the AOI
                aoi_track_coords = [
                    [float(lon), float(lat)]
                    for lon, lat in zip(lons_in_pass, lats_in_pass)
                    if aoi_geom.contains(Point(lon, lat))
                 ]
                
                if aoi_track_coords:
                    passes.append({
                        "start_time": current_pass["start_time"].utc_iso(),
                        "end_time": current_pass["end_time"].utc_iso(),
                        "max_elevation": current_pass.get("max_elevation"),
                        "track_coords": aoi_track_coords
                    })

                current_pass = {}

    return passes
 
ts = load.timescale()


# === Helper: footprint of one pass ===


def get_satellite_position(tle_line1, tle_line2):
    """
    Computes satellite's current position and its visible ground footprint radius.
    """
    satellite = EarthSatellite(tle_line1, tle_line2, 'satellite', ts)
    
    # Get the current time
    now = datetime.now(timezone.utc)
    time = ts.utc(now.year, now.month, now.day, now.hour, now.minute, now.second)
    
    # Get geocentric position
    geocentric = satellite.at(time)
    
    # Get subpoint position (lat, lon)
    subpoint = wgs84.subpoint(geocentric)
    lat = subpoint.latitude.degrees
    lon = subpoint.longitude.degrees
    altitude_m = wgs84.height_of(geocentric).m
    
    earth_radius_m = wgs84.radius.m
    
    
    
    # Calculate FOV radius using the provided formula
    half_angle_rad = math.acos(earth_radius_m / (earth_radius_m + altitude_m))
    fov_radius_m = earth_radius_m * half_angle_rad

    return {
        "latitude": lat,
        "longitude": lon,
        "fov_radius_m": fov_radius_m,
        "altitude_m": altitude_m   
    }
    
def OrbitalPath(tle_line1, tle_line2,duration_hours=24, step_seconds=30):
    """
    Computes the satellite's ground track over a specified duration.
    MVP: Defined duration and step seconds
    """
    satellite = EarthSatellite(tle_line1, tle_line2, 'satellite', ts)
    
    now = datetime.now(timezone.utc)
    end_time = now + timedelta(hours=duration_hours)
    
    times = ts.utc(pd.date_range(now, end_time, freq=f'{step_seconds}s'))
    
    geocentric = satellite.at(times)
    subpoints = wgs84.subpoint(geocentric)
    
    lats = subpoints.latitude.degrees
    lons = subpoints.longitude.degrees
    
    track_coords = [[float(lon), float(lat)] for lon, lat in zip(lons, lats)]
    
    return track_coords