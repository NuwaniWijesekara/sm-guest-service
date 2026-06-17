# ScanMe — Guest Service

Handles all guest-facing operations: loading event galleries and matching a guest's selfie against event photos using InsightFace ArcFace face recognition and pgvector cosine similarity search.

**Port:** `8002`  
**Stack:** FastAPI · PostgreSQL · pgvector · InsightFace ArcFace · ONNX Runtime

---

## What This Service Does

| Endpoint | Auth | Description |
|---|---|---|
| `GET /guest/{event_id}` | Public | Load event details and all photos by event ID |
| `GET /guest/validate/{qr_token}` | Public | Load event by QR token |
| `POST /match/selfie` | Public | Upload selfie → get matched photo URLs |
| `GET /health` | Public | Health check |

### Selfie matching flow

1. Guest uploads a selfie (JPEG/PNG/WebP, max 15 MB)
2. Service validates file size and MIME type
3. InsightFace extracts a 512-dimensional ArcFace embedding from the largest detected face
4. Raw selfie bytes are immediately deleted from memory (`del selfie_bytes`)
5. pgvector runs a cosine similarity search against all embeddings for that event
6. Matched photo URLs are returned — **nothing is stored**

> The selfie is processed entirely in memory and never written to disk, database, or S3.

---

## Project Structure

```
sm-guest/
├── app/
│   ├── main.py              # FastAPI app, loads InsightFace on startup
│   ├── models.py            # SQLAlchemy: Event, Image (read-only, no User)
│   ├── database.py          # Engine, SessionLocal, get_db
│   ├── api/
│   │   ├── guest.py         # GET /guest/:id and /guest/validate/:token
│   │   └── match.py         # POST /match/selfie — face search endpoint
│   ├── services/
│   │   └── face_engine.py   # InsightFace ArcFace singleton wrapper
│   └── config/
│       └── settings.py      # Pydantic settings loaded from .env
├── requirements.txt
├── Dockerfile
└── .env
```

---

## Environment Variables

Create a `.env` file in the root of this service:

```bash
# PostgreSQL — read-only queries on events + images tables
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/scanme_db

# Selfie matching thresholds
SIMILARITY_THRESHOLD=0.4         # cosine distance — lower = stricter (0.35–0.45 typical)
MAX_MATCH_RESULTS=50             # max photos returned per selfie search

# Selfie upload limit
MAX_SELFIE_BYTES=15728640        # 15 MB = 15 * 1024 * 1024

# Concurrency — max simultaneous InsightFace inference calls
# Tune to GPU VRAM: floor(VRAM_GB / 1.5) — buffalo_l uses ~1.2 GB per call
FACE_SEMAPHORE_LIMIT=4

# CORS
FRONTEND_ORIGIN=http://localhost:3000
```

---

## Running Manually (Local Development)

### Prerequisites

- Python 3.11+
- PostgreSQL running with `pgvector` extension
- Virtual environment activated
- InsightFace model weights (downloaded automatically on first run to `~/.insightface/`)

### Steps

```bash
# 1. Clone and enter the service
cd sm-guest

# 2. Create and activate virtual environment
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create .env file and fill in values
copy .env.example .env     # Windows
cp .env.example .env       # macOS/Linux

# 5. Run the service
uvicorn app.main:app --host 0.0.0.0 --port 8002 --reload
```

> **First run:** InsightFace will download `buffalo_l` model weights (~300 MB) to `C:\Users\<you>\.insightface\` on Windows or `~/.insightface/` on Linux/macOS. This happens once.

The service will be available at `http://localhost:8002`  
Interactive API docs at `http://localhost:8002/docs`

---

## Running with Docker

### GPU (recommended for production)

```bash
# Build
docker build -t scanme-guest .

# Run with GPU
docker run -p 8002:8002 --env-file .env --gpus all scanme-guest
```

### CPU only (development)

Change `onnxruntime-gpu` to `onnxruntime` in `requirements.txt` first, then:

```bash
docker build -t scanme-guest .
docker run -p 8002:8002 --env-file .env scanme-guest
```

### Run with infrastructure

```bash
# Start PostgreSQL first
docker-compose -f docker-compose-infra.yml up -d

# Then run this service
docker run -p 8002:8002 --env-file .env --network host scanme-guest
```

---

## Dependencies

| Package | Purpose |
|---|---|
| `fastapi` | HTTP framework |
| `uvicorn` | ASGI server |
| `sqlalchemy` | ORM (read-only queries) |
| `psycopg2-binary` | PostgreSQL driver |
| `pgvector` | `<=>` cosine distance operator |
| `insightface` | ArcFace face recognition model |
| `onnxruntime-gpu` | GPU inference (swap to `onnxruntime` for CPU) |
| `opencv-python-headless` | Image decode — headless = no GUI deps in Docker |
| `Pillow` | RGB conversion before InsightFace |
| `numpy` | Embedding normalization |
| `python-multipart` | UploadFile / Form parsing for selfie endpoint |
| `pydantic-settings` | `.env` → Settings class |

---

## Performance Notes

- InsightFace `buffalo_l` at 640×640 processes ~2–5 images/second on GPU
- The service runs `--workers 1` in Docker — GPU is a single shared resource; scale via container replicas not worker count
- `FACE_SEMAPHORE_LIMIT` caps concurrent inference calls to protect GPU VRAM
- The frontend pre-resizes selfies to 640×640 before upload, reducing server-side processing time

---

## Related Services

| Service | Repo | Description |
|---|---|---|
| Photographer Service | `scanme-photographer` | Auth, event management, QR tokens |
| Ingestion Worker | `scanme-ingestion-worker` | Processes photos and generates embeddings |
| API Gateway | `scanme-gateway` | Nginx routing on port 80 |
| Frontend | `scanme-frontend` | Next.js guest event page |

---

## Privacy

- Selfie bytes are deleted immediately after embedding extraction (`del selfie_bytes`)
- The 512-d query embedding is never written to the database, S3, or any storage
- Only S3 URLs of matched event photos are returned to the guest
- The footer of every guest page reads: *"Your selfie is never stored"*
