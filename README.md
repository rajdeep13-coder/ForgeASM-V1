# ForgeASM

ForgeASM is a configurable hardware architecture simulator for RISC-1,
RISC-2, RISC-3, and CISC instruction sets.

## Quick start

Create and activate a virtual environment from the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Start the API:

```powershell
python -m uvicorn api.main:app --reload
```

In a second terminal, start the frontend:

```powershell
cd frontend
npm ci
npm run dev
```

Open the URL printed by Vite, usually `http://localhost:5173`.

## Validation

Run the Python tests from the repository root:

```powershell
python -m pytest -q
```

Build the frontend:

```powershell
cd frontend
npm run build
```

## API

The interactive API documentation is available at
`http://127.0.0.1:8000/docs`.

ForgeASM assembles source code, creates isolated simulation sessions, and
supports stepping, running, resetting, memory inspection, trace inspection,
and captured program output. It does not require an AI provider or external
API key.

## License

Apache-2.0. See [LICENSE](LICENSE).
