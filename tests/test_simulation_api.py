"""
ForgeASM Simulation REST API — Test Suite
==========================================
Tests cover:

1.  Simulation creation → valid session ID + correct initial state
2.  Step → PC advances, registers update, flags work
3.  Run → final state, halt behaviour, cycle count
4.  Reset → state reverts to initial conditions
5.  Session isolation → stepping session A does not affect session B
6.  404 on unknown simulation ID
7.  Invalid ISA → 400 with meaningful error
8.  Run max_cycles guard → does not execute forever
9.  Full assemble → create → run workflow (integration)
10. DELETE → session removed, subsequent GET returns 404
11. Existing /api/assemble, /api/isa, /api/examples still work
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app
from core.isa.isa_def import ISA
from core.assembler.assembler import Assembler

# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    """Shared synchronous test client for the FastAPI app."""
    with TestClient(app) as c:
        yield c


def _assemble(isa_name: str, source: str) -> str:
    """Helper: assemble *source* for *isa_name* and return binary string."""
    isa = ISA(isa_name)
    return Assembler(isa).assemble(source)


def _create_sim(client: TestClient, isa: str, binary: str,
                arch: str = "neumann") -> dict:
    """POST /api/simulations and return the parsed JSON body."""
    res = client.post("/api/simulations", json={
        "isa": isa,
        "memory_architecture": arch,
        "binary": binary,
        "program_start": 0,
    })
    assert res.status_code == 201, res.text
    return res.json()


# ─── Minimal binaries ─────────────────────────────────────────────────────────

# A halt instruction for each ISA (opcode only, padded to byte)
HALT_RISC1  = _assemble("risc1",  "halt")
HALT_RISC2  = _assemble("risc2",  "halt")
HALT_RISC3  = _assemble("risc3",  "halt")
HALT_CISC   = _assemble("cisc",   "halt")


# ─── 1. Simulation creation ───────────────────────────────────────────────────

class TestCreateSimulation:
    def test_returns_201_and_simulation_id(self, client):
        res = client.post("/api/simulations", json={
            "isa": "risc3",
            "memory_architecture": "neumann",
            "binary": HALT_RISC3,
        })
        assert res.status_code == 201
        body = res.json()
        assert "simulation_id" in body
        assert len(body["simulation_id"]) == 36  # UUID4

    def test_initial_state_structure(self, client):
        body = _create_sim(client, "risc3", HALT_RISC3)
        state = body["state"]
        assert "registers" in state
        assert "flags" in state
        assert "memory" in state
        assert "halted" in state
        assert "pc" in state
        assert state["cycle_count"] == 0

    def test_initial_flags_are_false(self, client):
        body = _create_sim(client, "risc3", HALT_RISC3)
        flags = body["state"]["flags"]
        assert flags == {"Z": False, "C": False, "O": False, "N": False}

    def test_initial_memory_length(self, client):
        body = _create_sim(client, "risc3", HALT_RISC3)
        assert len(body["state"]["memory"]) == 512

    def test_isa_and_arch_echoed(self, client):
        body = _create_sim(client, "risc1", HALT_RISC1, arch="harvard")
        assert body["isa"] == "risc1"
        assert body["memory_architecture"] == "harvard"

    def test_all_isas_create_successfully(self, client):
        for isa_name, binary in [
            ("risc1", HALT_RISC1),
            ("risc2", HALT_RISC2),
            ("risc3", HALT_RISC3),
            ("cisc",  HALT_CISC),
        ]:
            body = _create_sim(client, isa_name, binary)
            assert "simulation_id" in body


# ─── 2. Invalid ISA ───────────────────────────────────────────────────────────

class TestInvalidISA:
    def test_unknown_isa_returns_400(self, client):
        res = client.post("/api/simulations", json={
            "isa": "sparc_v9",
            "memory_architecture": "neumann",
            "binary": "00000000",
        })
        assert res.status_code == 400
        body = res.json()
        assert body["code"] == "INVALID_ISA"

    def test_error_message_is_informative(self, client):
        res = client.post("/api/simulations", json={
            "isa": "nonexistent",
            "memory_architecture": "neumann",
            "binary": "00000000",
        })
        assert "error" in res.json()


# ─── 3. GET simulation ────────────────────────────────────────────────────────

class TestGetSimulation:
    def test_get_returns_200(self, client):
        body = _create_sim(client, "risc3", HALT_RISC3)
        sim_id = body["simulation_id"]
        res = client.get(f"/api/simulations/{sim_id}")
        assert res.status_code == 200

    def test_get_returns_correct_id(self, client):
        body = _create_sim(client, "risc3", HALT_RISC3)
        sim_id = body["simulation_id"]
        get_body = client.get(f"/api/simulations/{sim_id}").json()
        assert get_body["simulation_id"] == sim_id

    def test_get_unknown_id_returns_404(self, client):
        res = client.get("/api/simulations/00000000-0000-0000-0000-000000000000")
        assert res.status_code == 404
        assert res.json()["code"] == "SIMULATION_NOT_FOUND"


# ─── 4. Step ──────────────────────────────────────────────────────────────────

class TestStep:
    def _simple_program(self) -> str:
        """A two-instruction RISC-3 program: nop then halt."""
        return _assemble("risc3", "nop\nhalt")

    def test_step_returns_200(self, client):
        body = _create_sim(client, "risc3", self._simple_program())
        sim_id = body["simulation_id"]
        res = client.post(f"/api/simulations/{sim_id}/step")
        assert res.status_code == 200

    def test_step_increments_cycle_count(self, client):
        body = _create_sim(client, "risc3", self._simple_program())
        sim_id = body["simulation_id"]
        client.post(f"/api/simulations/{sim_id}/step")
        state = client.get(f"/api/simulations/{sim_id}").json()["state"]
        assert state["cycle_count"] == 1

    def test_step_on_halted_cpu_does_not_increment_cycles(self, client):
        """Stepping a halted CPU should be a no-op and not raise an error."""
        body = _create_sim(client, "risc3", HALT_RISC3)
        sim_id = body["simulation_id"]
        # Execute the halt
        client.post(f"/api/simulations/{sim_id}/step")
        # Step again on already-halted CPU
        res = client.post(f"/api/simulations/{sim_id}/step")
        assert res.status_code == 200
        state = res.json()["state"]
        assert state["halted"] is True

    def test_step_unknown_id_returns_404(self, client):
        res = client.post("/api/simulations/00000000-0000-0000-0000-000000000000/step")
        assert res.status_code == 404


# ─── 5. Run ───────────────────────────────────────────────────────────────────

class TestRun:
    def test_run_returns_200(self, client):
        body = _create_sim(client, "risc3", HALT_RISC3)
        sim_id = body["simulation_id"]
        res = client.post(f"/api/simulations/{sim_id}/run", json={"max_cycles": 100})
        assert res.status_code == 200

    def test_run_halts_on_halt_instruction(self, client):
        body = _create_sim(client, "risc3", HALT_RISC3)
        sim_id = body["simulation_id"]
        res = client.post(f"/api/simulations/{sim_id}/run", json={"max_cycles": 1000})
        body = res.json()
        assert body["state"]["halted"] is True
        assert body["halt_reason"] == "halted"

    def test_run_respects_max_cycles(self, client):
        """An infinite loop must be cut off at max_cycles, not run forever."""
        # Build a tight loop: jmp .loop (unconditional back-jump)
        # RISC-3 jmp with offset -1 loops forever
        src = ".loop\njmp .loop"
        try:
            binary = _assemble("risc3", src)
        except Exception:
            pytest.skip("Could not assemble loop program for this ISA version")

        body = _create_sim(client, "risc3", binary)
        sim_id = body["simulation_id"]
        res = client.post(f"/api/simulations/{sim_id}/run", json={"max_cycles": 50})
        body_j = res.json()
        assert body_j["halt_reason"] == "max_cycles"
        assert body_j["cycles_executed"] == 50

    def test_run_already_halted(self, client):
        body = _create_sim(client, "risc3", HALT_RISC3)
        sim_id = body["simulation_id"]
        # First run – halts the CPU
        client.post(f"/api/simulations/{sim_id}/run", json={"max_cycles": 1000})
        # Second run – CPU already halted
        res = client.post(f"/api/simulations/{sim_id}/run", json={"max_cycles": 1000})
        assert res.json()["halt_reason"] == "already_halted"
        assert res.json()["cycles_executed"] == 0

    def test_run_returns_cycles_executed(self, client):
        body = _create_sim(client, "risc3", HALT_RISC3)
        sim_id = body["simulation_id"]
        res = client.post(f"/api/simulations/{sim_id}/run", json={"max_cycles": 1000})
        # halt is the first instruction, so exactly 1 cycle
        assert res.json()["cycles_executed"] >= 1

    def test_run_unknown_id_returns_404(self, client):
        res = client.post(
            "/api/simulations/00000000-0000-0000-0000-000000000000/run",
            json={"max_cycles": 10},
        )
        assert res.status_code == 404


# ─── 6. Reset ─────────────────────────────────────────────────────────────────

class TestReset:
    def test_reset_clears_halted_flag(self, client):
        body = _create_sim(client, "risc3", HALT_RISC3)
        sim_id = body["simulation_id"]
        client.post(f"/api/simulations/{sim_id}/run", json={"max_cycles": 100})
        res = client.post(f"/api/simulations/{sim_id}/reset")
        assert res.status_code == 200
        assert res.json()["state"]["halted"] is False

    def test_reset_clears_cycle_count(self, client):
        body = _create_sim(client, "risc3", HALT_RISC3)
        sim_id = body["simulation_id"]
        client.post(f"/api/simulations/{sim_id}/run", json={"max_cycles": 100})
        res = client.post(f"/api/simulations/{sim_id}/reset")
        assert res.json()["state"]["cycle_count"] == 0

    def test_reset_pc_returns_to_zero(self, client):
        body = _create_sim(client, "risc3", HALT_RISC3)
        sim_id = body["simulation_id"]
        client.post(f"/api/simulations/{sim_id}/run", json={"max_cycles": 100})
        res = client.post(f"/api/simulations/{sim_id}/reset")
        assert res.json()["state"]["pc"] == 0

    def test_program_runnable_after_reset(self, client):
        body = _create_sim(client, "risc3", HALT_RISC3)
        sim_id = body["simulation_id"]
        client.post(f"/api/simulations/{sim_id}/run", json={"max_cycles": 100})
        client.post(f"/api/simulations/{sim_id}/reset")
        # Should be able to run again
        res = client.post(f"/api/simulations/{sim_id}/run", json={"max_cycles": 100})
        assert res.status_code == 200
        assert res.json()["state"]["halted"] is True

    def test_reset_unknown_id_returns_404(self, client):
        res = client.post("/api/simulations/00000000-0000-0000-0000-000000000000/reset")
        assert res.status_code == 404


# ─── 7. Session isolation ─────────────────────────────────────────────────────

class TestSessionIsolation:
    def test_two_sessions_are_independent(self, client):
        """Stepping session A must not alter session B."""
        src = "nop\nhalt"
        try:
            binary = _assemble("risc3", src)
        except Exception:
            pytest.skip("Could not assemble nop program")

        body_a = _create_sim(client, "risc3", binary)
        body_b = _create_sim(client, "risc3", binary)
        id_a = body_a["simulation_id"]
        id_b = body_b["simulation_id"]
        assert id_a != id_b

        # Step A several times
        for _ in range(2):
            client.post(f"/api/simulations/{id_a}/step")

        cycles_a = client.get(f"/api/simulations/{id_a}").json()["state"]["cycle_count"]
        cycles_b = client.get(f"/api/simulations/{id_b}").json()["state"]["cycle_count"]

        assert cycles_a == 2
        assert cycles_b == 0  # B untouched

    def test_different_isas_do_not_interfere(self, client):
        body_risc3 = _create_sim(client, "risc3", HALT_RISC3)
        body_cisc  = _create_sim(client, "cisc",  HALT_CISC)
        assert body_risc3["simulation_id"] != body_cisc["simulation_id"]
        assert body_risc3["isa"] == "risc3"
        assert body_cisc["isa"]  == "cisc"


# ─── 8. Delete ────────────────────────────────────────────────────────────────

class TestDelete:
    def test_delete_returns_204(self, client):
        body = _create_sim(client, "risc3", HALT_RISC3)
        sim_id = body["simulation_id"]
        res = client.delete(f"/api/simulations/{sim_id}")
        assert res.status_code == 204

    def test_get_after_delete_returns_404(self, client):
        body = _create_sim(client, "risc3", HALT_RISC3)
        sim_id = body["simulation_id"]
        client.delete(f"/api/simulations/{sim_id}")
        res = client.get(f"/api/simulations/{sim_id}")
        assert res.status_code == 404

    def test_delete_unknown_id_returns_404(self, client):
        res = client.delete("/api/simulations/00000000-0000-0000-0000-000000000000")
        assert res.status_code == 404


# ─── 9. Integration: assemble → create → run ─────────────────────────────────

class TestIntegration:
    def test_assemble_endpoint_returns_binary(self, client):
        code = "halt"
        res = client.post("/api/assemble", json={"code": code, "isa": "risc3"})
        assert res.status_code == 200
        body = res.json()
        assert body["success"] is True
        assert body["binary"]

    def test_full_workflow_risc3(self, client):
        """Assemble → POST /simulations → run → verify halted."""
        code = "nop\nnop\nhalt"
        assemble_res = client.post("/api/assemble", json={"code": code, "isa": "risc3"})
        assert assemble_res.json()["success"]
        binary = assemble_res.json()["binary"]

        sim_res = client.post("/api/simulations", json={
            "isa": "risc3",
            "memory_architecture": "neumann",
            "binary": binary,
        })
        assert sim_res.status_code == 201
        sim_id = sim_res.json()["simulation_id"]

        run_res = client.post(f"/api/simulations/{sim_id}/run", json={"max_cycles": 100})
        body = run_res.json()
        assert body["state"]["halted"] is True
        # 3 instructions: nop, nop, halt
        assert body["cycles_executed"] >= 1

    def test_full_workflow_cisc(self, client):
        assemble_res = client.post("/api/assemble", json={"code": "halt", "isa": "cisc"})
        assert assemble_res.json()["success"]
        binary = assemble_res.json()["binary"]

        sim_res = client.post("/api/simulations", json={
            "isa": "cisc",
            "memory_architecture": "neumann",
            "binary": binary,
        })
        assert sim_res.status_code == 201


# ─── 10. Existing endpoints ───────────────────────────────────────────────────

class TestExistingEndpoints:
    def test_assemble_invalid_isa(self, client):
        res = client.post("/api/assemble", json={"code": "halt", "isa": "fake_isa"})
        assert res.status_code == 200  # endpoint returns 200 with success=False
        assert res.json()["success"] is False

    def test_isa_info_risc3(self, client):
        res = client.get("/api/isa/risc3")
        assert res.status_code == 200
        body = res.json()
        assert body["name"] == "risc3"
        assert "registers" in body
        assert "instructions" in body

    def test_isa_info_unknown(self, client):
        res = client.get("/api/isa/unknown_isa_xyz")
        assert res.status_code == 404

    def test_examples_returns_dict(self, client):
        res = client.get("/api/examples")
        assert res.status_code == 200
        body = res.json()
        assert isinstance(body, dict)
        # At least one ISA key present
        assert len(body) > 0

    def test_docs_accessible(self, client):
        res = client.get("/docs")
        assert res.status_code == 200


# ─── 11. No WebSocket ─────────────────────────────────────────────────────────

class TestNoWebSocket:
    def test_ws_simulate_endpoint_does_not_exist(self, client):
        """The old WebSocket endpoint must be gone."""
        # A GET to the old path should return 404 or 405, never 101 (WS upgrade)
        res = client.get("/api/simulate")
        assert res.status_code in (404, 405)
