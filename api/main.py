"""
ForgeASM — FastAPI Application Entry Point
==========================================
Dependency graph:
    HTTP client (React frontend)
        └── FastAPI app   (this file)
                ├── /api/assemble          (inline route – simple stateless transform)
                ├── /api/isa/{name}        (inline route – read-only ISA metadata)
                ├── /api/examples          (inline route – static file serving)
                └── /api/simulations/*     (simulation router – see api/routes/simulation.py)
                        └── SimulationManager
                                └── CPU / Memory / IO  (core/)

The ForgeASM Core (core/) is completely transport-agnostic.  It does not
import FastAPI, Pydantic, or anything from the api/ layer.
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from api.models import AssembleRequest, AssembleResponse
from api.routes.simulation import router as simulation_router
from core.isa.isa_def import ISA
from core.isa.exceptions import InvalidISAError
from core.assembler.assembler import Assembler


# ─── Application ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="ForgeASM — Hardware Simulator API",
    description=(
        "REST API for the ForgeASM configurable hardware architecture simulator. "
        "Supports RISC-1 (stack), RISC-2 (accumulator), RISC-3 (register), and CISC "
        "instruction sets with Von Neumann and Harvard memory architectures."
    ),
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)


# ─── CORS ─────────────────────────────────────────────────────────────────────
# Allow configuration via environment variables for flexible deployment.
# Default: allow all origins (suitable for development / single-origin proxy).

_raw_origins = os.environ.get("CORS_ORIGINS", "*")
_allow_origins = (
    [o.strip() for o in _raw_origins.split(",")]
    if _raw_origins != "*"
    else ["*"]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Routers ──────────────────────────────────────────────────────────────────

app.include_router(simulation_router)


# ─── Assemble ─────────────────────────────────────────────────────────────────

@app.post(
    "/api/assemble",
    response_model=AssembleResponse,
    tags=["Assembler"],
    summary="Assemble source code into binary",
)
async def assemble_code(req: AssembleRequest) -> AssembleResponse:
    """
    Parse and encode assembly source code for the specified ISA.

    Returns a newline-separated string of binary bit strings — one per encoded
    instruction word — suitable for passing directly to ``POST /api/simulations``.
    """
    try:
        isa = ISA(req.isa.lower())
        assembler = Assembler(isa)
        binary = assembler.assemble(req.code)
        return AssembleResponse(binary=binary, success=True)
    except InvalidISAError as exc:
        return AssembleResponse(binary="", error=str(exc), success=False)
    except Exception as exc:
        return AssembleResponse(binary="", error=str(exc), success=False)


# ─── ISA metadata ─────────────────────────────────────────────────────────────

@app.get(
    "/api/isa/{name}",
    tags=["ISA"],
    summary="Get register and instruction definitions for an ISA",
    responses={404: {"description": "ISA not found"}},
)
async def get_isa_info(name: str) -> JSONResponse:
    """
    Return the full register set and instruction table for a given ISA.

    Useful for building syntax highlighting, autocomplete, or documentation.
    """
    try:
        isa = ISA(name.lower())
    except InvalidISAError as exc:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": str(exc), "code": "INVALID_ISA"},
        )

    registers = [
        {
            "name": reg.name,
            "is_general_purpose": reg.is_general_purpose,
            "encoding": reg.encoding,
            "description": reg.description,
        }
        for reg in isa.registers.values()
    ]
    instructions = [
        {
            "opcode": opcode,
            "name": inst.name,
            "result_dest": inst.result_dest,
            "operands": inst.operands,
        }
        for opcode, inst in isa.instructions.items()
    ]
    return JSONResponse(
        content={
            "name": isa.name,
            "registers": registers,
            "instructions": instructions,
        }
    )


# ─── Example programs ─────────────────────────────────────────────────────────

@app.get(
    "/api/examples",
    tags=["Examples"],
    summary="Get example assembly programs for each ISA",
)
async def get_examples() -> JSONResponse:
    """
    Return a dictionary of example programs keyed by ISA name.

    Each entry is a list of ``{name, code}`` objects.
    """
    isas = ["risc1", "risc2", "risc3", "cisc"]
    program_names = ["alphabet_printout", "helloworld", "bubble_sort", "polynomial"]

    base_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "modules", "demos"
    )

    examples: Dict[str, List[Dict[str, str]]] = {}
    for isa_name in isas:
        isa_examples: List[Dict[str, str]] = []
        for prog in program_names:
            filepath = os.path.join(base_dir, isa_name, f"{prog}.asm")
            try:
                with open(filepath, "r") as fh:
                    code = fh.read()
                display_name = prog.replace("_", " ").title()
                isa_examples.append({"name": display_name, "code": code})
            except FileNotFoundError:
                pass
        examples[isa_name] = isa_examples

    return JSONResponse(content=examples)


# ─── Frontend static files (same-origin SPA) ──────────────────────────────────

_REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
_FRONTEND_DIST = os.path.join(_REPO_ROOT, "frontend", "dist")
_FRONTEND_ASSETS = os.path.join(_FRONTEND_DIST, "assets")

# Mount /assets so Vite's hashed JS/CSS bundles are served correctly
if os.path.isdir(_FRONTEND_ASSETS):
    app.mount("/assets", StaticFiles(directory=_FRONTEND_ASSETS), name="assets")


@app.get("/{full_path:path}", include_in_schema=False)
async def serve_spa(full_path: str) -> FileResponse:
    """
    SPA catch-all: serve index.html for every route that is not an /api path.
    This enables React Router (or direct URL loads) to work correctly.

    Must be registered AFTER all /api routes.
    """
    # Never intercept API, docs, or openapi routes
    blocked = ("api/", "docs", "redoc", "openapi.json")
    if any(full_path.startswith(b) for b in blocked):
        raise HTTPException(status_code=404, detail="Not found")

    index_path = os.path.join(_FRONTEND_DIST, "index.html")
    if os.path.isfile(index_path):
        return FileResponse(index_path)

    # Frontend hasn't been built yet — return a helpful JSON message
    return JSONResponse(
        status_code=200,
        content={
            "message": "Frontend not built. Run: cd frontend && npm run build",
            "hint": "The API is available at /api/*",
        },
    )
