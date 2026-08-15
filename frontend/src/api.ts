/**
 * ForgeASM REST API client
 * ========================
 * Pure HTTP/REST — no WebSockets anywhere.
 *
 * All simulation state originates from the Python ForgeASM core.
 * The frontend is strictly a visualisation layer.
 */

const BASE = (import.meta.env.VITE_API_URL as string) ?? '';

// ─── Low-level fetch wrapper ──────────────────────────────────────────────────

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method, headers: { 'Content-Type': 'application/json' } };
  if (body !== undefined) init.body = JSON.stringify(body);

  const res = await fetch(`${BASE}${path}`, init);
  if (res.status === 204) return null as T;

  const data = await res.json();
  if (!res.ok) {
    const msg: string = data?.error ?? data?.detail ?? `HTTP ${res.status}`;
    throw new APIError(msg, data?.code ?? 'HTTP_ERROR', res.status);
  }
  return data as T;
}

// ─── Typed error ─────────────────────────────────────────────────────────────

export class APIError extends Error {
  readonly code: string;
  readonly httpStatus: number;
  constructor(message: string, code: string, httpStatus: number) {
    super(message);
    this.name = 'APIError';
    this.code = code;
    this.httpStatus = httpStatus;
  }
}

// ─── Domain types ─────────────────────────────────────────────────────────────

export interface AssembleResult {
  binary: string;
  error: string | null;
  success: boolean;
}

export interface ExampleProgram {
  name: string;
  code: string;
}

export type ExamplesByISA = Record<string, ExampleProgram[]>;

/**
 * Snapshot of the full CPU state returned by every simulation endpoint.
 * All fields are optional-friendly since different ISAs expose different registers.
 * The `flags` record is keyed by flag name (e.g. "Z", "C", "O", "N") and
 * contains boolean values — rendered dynamically, not hardcoded.
 */
export interface SimState {
  pc: number;
  registers: Record<string, number>;
  /** Dynamic: keyed by flag name, value is boolean. Do NOT assume Z/C/O/N. */
  flags: Record<string, boolean>;
  memory: number[];
  halted: boolean;
  output: string;
  cycle_count: number;
  /** Instruction name sitting at current PC — next to execute on step. */
  current_instruction: string | null;
}

export interface SimulationSession {
  simulation_id: string;
  isa: string;
  memory_architecture: string;
  state: SimState;
}

export interface StepResult {
  simulation_id: string;
  state: SimState;
  /** Instruction name that was just executed (before the step). */
  last_instruction: string | null;
}

export interface RunResult {
  simulation_id: string;
  state: SimState;
  cycles_executed: number;
  halt_reason: 'halted' | 'max_cycles' | 'already_halted';
}

// ─── Assembler ────────────────────────────────────────────────────────────────

export async function assembleCode(code: string, isa: string): Promise<AssembleResult> {
  return request<AssembleResult>('POST', '/api/assemble', { code, isa });
}

export async function getExamples(): Promise<ExamplesByISA> {
  return request<ExamplesByISA>('GET', '/api/examples');
}

// ─── Simulation session ───────────────────────────────────────────────────────

export async function createSimulation(
  isa: string, memoryArchitecture: string, binary: string, programStart = 0,
): Promise<SimulationSession> {
  return request<SimulationSession>('POST', '/api/simulations', {
    isa, memory_architecture: memoryArchitecture, binary, program_start: programStart,
  });
}

export async function stepSimulation(simulationId: string): Promise<StepResult> {
  return request<StepResult>('POST', `/api/simulations/${simulationId}/step`);
}

export async function runSimulation(simulationId: string, maxCycles = 10000): Promise<RunResult> {
  return request<RunResult>('POST', `/api/simulations/${simulationId}/run`, { max_cycles: maxCycles });
}

export async function resetSimulation(simulationId: string): Promise<{ simulation_id: string; state: SimState }> {
  return request('POST', `/api/simulations/${simulationId}/reset`);
}

export async function deleteSimulation(simulationId: string): Promise<void> {
  return request('DELETE', `/api/simulations/${simulationId}`);
}
