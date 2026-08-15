# ForgeASM

A configurable hardware architecture simulator and assembler.  
Write assembly, assemble it to machine code, load it into a simulated CPU, and step through execution — all from a browser.

---

## What Is ForgeASM?

ForgeASM is a computer-architecture learning tool that implements four distinct instruction set architectures (ISAs) from scratch, each with its own register file, instruction encoding, and execution model.  It lets you:

- Write assembly source code in an in-browser editor
- Assemble it to a binary using a multi-pass assembler
- Execute it on a cycle-accurate CPU simulator
- Inspect registers, flags, and memory in real time

---

## Architecture

```
Assembly Source
     │
     ▼
 Assembler  ──────────────────────────────────────────────────────┐
     │                                                            │
     │  Binary (newline-separated bit strings)                   │
     ▼                                                            │
 POST /api/simulations                                           │
     │                                                            │
     ▼                                                            │
 SimulationManager  (in-memory session store)                    │
     │                                                            │
     ▼                                                            │
 Simulation                                                       │
     ├── CPU  ─────────── registers / ALU / flags / PC           │
     ├── Memory  ─────── Von Neumann | Harvard                   │
     └── I/O  ────────── Memory-mapped I/O                       │
                                                                  │
ForgeASM Core  ◄──────────────────────────────────────────────────┘
(completely transport-agnostic: no FastAPI, no HTTP, no sockets)
```

The core simulation engine (`core/`) has zero knowledge of HTTP or the frontend.  The FastAPI layer is purely a transport adapter on top of it.

---

## Supported ISAs

| ISA    | Architecture       | Key Feature                   |
|--------|--------------------|-------------------------------|
| RISC-1 | Stack              | Operands implicitly from TOS  |
| RISC-2 | Accumulator        | Single accumulator register   |
| RISC-3 | Register-register  | General-purpose register file |
| CISC   | Register + memory  | Multi-byte variable-length instructions |

Both **Von Neumann** (unified instruction/data memory) and **Harvard** (separate instruction/data buses) memory architectures are supported.

---

## REST API

The simulation is controlled entirely over HTTP.  There are no WebSockets.

### Assembler

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/assemble` | Assemble source code → binary |
| `GET`  | `/api/isa/{name}` | Register and instruction definitions |
| `GET`  | `/api/examples` | Example programs for each ISA |

### Simulation Lifecycle

| Method   | Path | Description |
|----------|------|-------------|
| `POST`   | `/api/simulations` | Create and initialize a simulation session |
| `GET`    | `/api/simulations/{id}` | Inspect current CPU state |
| `POST`   | `/api/simulations/{id}/step` | Execute exactly one instruction |
| `POST`   | `/api/simulations/{id}/run` | Run up to `max_cycles` instructions |
| `POST`   | `/api/simulations/{id}/reset` | Reset CPU to initial loaded state |
| `DELETE` | `/api/simulations/{id}` | Delete the session |

Interactive documentation is available at **`/docs`** (Swagger UI) and **`/redoc`** when the backend is running.

### Example: full workflow

```bash
# 1. Assemble
curl -X POST http://localhost:8000/api/assemble \
  -H 'Content-Type: application/json' \
  -d '{"code": "nop\nhalt", "isa": "risc3"}'

# 2. Create simulation (paste binary from step 1)
curl -X POST http://localhost:8000/api/simulations \
  -H 'Content-Type: application/json' \
  -d '{"isa":"risc3","memory_architecture":"neumann","binary":"..."}'

# 3. Step
curl -X POST http://localhost:8000/api/simulations/{id}/step

# 4. Run
curl -X POST http://localhost:8000/api/simulations/{id}/run \
  -d '{"max_cycles":1000}'

# 5. Reset
curl -X POST http://localhost:8000/api/simulations/{id}/reset

# 6. Clean up
curl -X DELETE http://localhost:8000/api/simulations/{id}
```

---

## Local Development

### Prerequisites

- Python 3.11+
- Node.js 18+

### Backend

```bash
# Install dependencies
pip install -r requirements.txt

# Start the FastAPI server (with hot reload)
uvicorn api.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

### Frontend

```bash
cd frontend
npm install
npm run dev
```

App: http://localhost:5173  
The Vite dev server proxies all `/api` requests to the backend automatically.

### Run Tests

```bash
# All backend tests (46 tests)
python -m pytest tests/ -v
```

---

## Project Structure

```
ForgeASM-V1/
├── api/
│   ├── main.py                  # FastAPI app entry point
│   ├── models.py                # Pydantic request/response models
│   ├── simulation_manager.py    # Session store + transport-agnostic engine
│   └── routes/
│       └── simulation.py        # REST simulation endpoints
│
├── core/
│   ├── assembler/               # Multi-pass assembler + parser
│   ├── isa/                     # ISA definitions (JSON + Python)
│   ├── memory/                  # Von Neumann / Harvard memory banks
│   ├── io/                      # Memory-mapped and port-mapped I/O
│   └── simulator/               # CPU fetch-decode-execute engine
│
├── frontend/
│   └── src/
│       ├── api.ts               # REST API client (no WebSocket)
│       ├── App.tsx              # React IDE
│       └── App.css              # LeetCode-inspired dark theme
│
├── tests/
│   ├── test_assembler.py        # Assembler unit tests
│   ├── test_isa.py              # ISA loader unit tests
│   └── test_simulation_api.py   # REST API integration tests (40 tests)
│
└── modules/demos/               # Example .asm programs per ISA
```

---

## Deployment

### Production build

```bash
# Build frontend static assets
cd frontend && npm run build

# Serve static assets via FastAPI (or any CDN/static host)
# Backend: single Uvicorn process, no Redis or database required
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CORS_ORIGINS` | `*` | Comma-separated allowed origins (e.g. `https://yoursite.com`) |
| `VITE_API_URL` | `""` (same origin) | Backend URL for frontend builds behind a CDN |

The application **does not require** Redis, a database, a message queue, or WebSocket support.  A single Python process is sufficient for V1.

---

## Session Management Note

Simulation sessions are stored in the server process's heap memory.  This is intentional for V1 simplicity.  A single Uvicorn worker (`--workers 1`) is the correct deployment target.  For multi-instance horizontal scaling, replace the in-memory dict in `SimulationManager` with an external store (e.g. Redis).

---

## Known Limitations

- Sessions are lost on server restart (in-memory store).
- The CPU simulator covers the primary instruction set; some edge-case opcodes fall through to no-ops rather than raising errors.
- No authentication — the API is open.  Do not expose it directly to the public internet without a reverse proxy.

---

## Future Improvements

- Persist sessions across restarts (Redis or SQLite)
- Pipeline simulation (fetch/decode/execute stages with hazard detection)
- VCD waveform export for signal visualization
- Syntax highlighting in the editor (CodeMirror or Monaco)
- Breakpoint support in the debugger
