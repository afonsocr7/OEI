# Orbital Edge Imaging – Pass Prediction Tool

This project is a web-based application to upload, manage, and visualize **satellite TLEs** and **Areas of Interest (AOIs)**, and compute upcoming satellite passes over selected AOIs.  

It combines:
- **Backend**: [FastAPI](https://fastapi.tiangolo.com/) with SQLAlchemy & PostGIS  
- **Frontend**: [Leaflet.js](https://leafletjs.com/) for interactive maps  
- **Database**: PostgreSQL + PostGIS (via Docker)  
- **Containerization**: Docker Compose  

---

## Features

✅ Upload TLE files (`.txt`) and store them in the database  
✅ Upload AOI files (`.geojson`) and store them in the database  
✅ Dropdown menus to select stored TLEs and AOIs  
✅ Compute and display **upcoming satellite passes** over AOIs  
✅ Interactive Leaflet map to visualize AOIs and satellite tracks  
✅ PostgreSQL + PostGIS backend for spatial queries  
✅ pgAdmin included for easy database inspection  

---

## Project Structure


├── backend/app/
│ ├── main.py # FastAPI entrypoint
│ ├── models.py # SQLAlchemy ORM models (TLE, AOI)
│ ├── database.py # Database connection/session
│ ├── schemas.py # Pydantic schemas for request/response validation
│ ├── utils.py # Compute passes, orbital path, satellite tracking
│ └── ...
├── frontend/
│ ├── index.html # Main UI
│ ├── main.ts # Frontend logic (map, API calls)
│ └── styles.css # Styling
├── docker-compose.yml # Multi-service orchestration
└── README.md # Documentation


---

## Getting Started

### 1. Clone the repository
```bash
git clone https://github.com/your-username/orbital-edge-imaging.git
cd orbital-edge-imaging


2. Start services with Docker

docker-compose up --build

This will spin up:

db: PostgreSQL with PostGIS
frontend: frontend served (http://localhost:3000)
pgadmin: Database admin panel (http://localhost:5050)

API endpoints

| Method | Endpoint               | Description                                           |
| ------ | ---------------------- | ----------------------------------------------------- |
| POST   | `/tle/upload`          | Upload TLE file (.txt)                                |
| GET    | `/tles`                | List all TLEs                                         |
| POST   | `/geojson`             | Upload AOI (.geojson)                                 |
| GET    | `/aois`                | List all AOIs                                         |
| GET    | `/aois/{aoi_id}`       | Get AOI details + geometry as GeoJSON                 |
| POST   | `/passes`              | Compute upcoming passes for selected TLE + AOI        |
| GET    | `/track`               | Get **current position** of a satellite (by NORAD ID) |
| GET    | `/OrbitalPath/{norad}` | Get **orbital path** for a satellite (by NORAD ID)    |

Frontend Usage

1. Open http://localhost:3000
2. Upload a TLE (.txt) or choose an existing one from the dropdown
3. Upload a GeoJSON AOI file or select one from the dropdown
4. Click Compute Passes to see results
5. Passes will be shown both on the map and in a results table

Resetting the Database

To wipe everything (fresh DB + pgAdmin data):

```bash
docker-compose down -v
docker-compose up --build

Notes

AOIs are stored with SRID=4326 in PostGIS.
The backend computes passes using Skyfield (satellite propagation).
You can inspect the database directly in pgAdmin at http://localhost:5050
