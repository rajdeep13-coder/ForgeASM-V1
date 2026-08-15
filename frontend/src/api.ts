/**
 * ForgeASM REST API client
 * ========================
 * All communication with the backend is HTTP/REST.  There are no WebSockets.
 *
 * The base URL is read from the Vite env variable VITE_API_URL at build time.
 * In development the Vite proxy rewrites /api → http://localhost:8000, so the
 * default empty string ("same origin") works out of the box.
 */

const BASE = (import.meta.env.VITE_API_URL as string) ?? '';

// ─── Low-level fetch wrapper ──────────────────────────────────────────────────

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const init: RequestInit = {
    method,
    headers: { 'Content-Type': 'application/json' },
  };
  if (body !== undefined) {
    init.body = JSON.stringify(body);
  }

  const res = await fetch(`${BASE}${path}`, init);

  // 204 No Content – return null
  if (res.status === 204) return null as T;

  const data = await res.json();

  if (!res.ok) {
    // Structured error from the API
    const msg: string =
      data?.error ?? data?.detail ?? `HTTP ${res.status}`;
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

export interface FlagsSnapshot {
  Z: boolean;
  C: boolean;
  O: boolean;
  N: boolean;
}

export interface SimState {
  pc: number;
  registers: Record<string, number>;
  flags: FlagsSnapshot;
  memory: number[];
  halted: boolean;
  output: string;
  cycle_count: number;
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
  last_instruction: string | null;
}

export interface RunResult {
  simulation_id: string;
  state: SimState;
  cycles_executed: number;
  halt_reason: 'halted' | 'max_cycles' | 'already_halted';
}

// ─── Assembler ────────────────────────────────────────────────────────────────

export async function assembleCode(
  code: string,
  isa: string,
): Promise<AssembleResult> {
  return request<AssembleResult>('POST', '/api/assemble', { code, isa });
}

// ─── ISA metadata ─────────────────────────────────────────────────────────────

export async function getISAInfo(name: string): Promise<unknown> {
  return request<unknown>('GET', `/api/isa/${name}`);
}

// ─── Example programs ─────────────────────────────────────────────────────────

export async function getExamples(): Promise<ExamplesByISA> {
  return request<ExamplesByISA>('GET', '/api/examples');
}

// ─── Simulation session ───────────────────────────────────────────────────────

/**
 * Create a new simulation session and load the binary into memory.
 * Returns the session (including its unique simulation_id).
 */
export async function createSimulation(
  isa: string,
  memoryArchitecture: string,
  binary: string,
  programStart = 0,
): Promise<SimulationSession> {
  return request<SimulationSession>('POST', '/api/simulations', {
    isa,
    memory_architecture: memoryArchitecture,
    binary,
    program_start: programStart,
  });
}

/**
 * Fetch the current state of an existing simulation without executing anything.
 */
export async function getSimulation(
  simulationId: string,
): Promise<SimulationSession> {
  return request<SimulationSession>('GET', `/api/simulations/${simulationId}`);
}

/**
 * Execute exactly one instruction and return the new state.
 */
export async function stepSimulation(simulationId: string): Promise<StepResult> {
  return request<StepResult>('POST', `/api/simulations/${simulationId}/step`);
}

/**
 * Execute up to maxCycles instructions and return the final state.
 */
export async function runSimulation(
  simulationId: string,
  maxCycles = 1000,
): Promise<RunResult> {
  return request<RunResult>('POST', `/api/simulations/${simulationId}/run`, {
    max_cycles: maxCycles,
  });
}

/**
 * Reset the CPU to its initial state (registers, flags, memory all cleared).
 * The original binary is reloaded automatically.
 */
export async function resetSimulation(
  simulationId: string,
): Promise<{ simulation_id: string; state: SimState }> {
  return request('POST', `/api/simulations/${simulationId}/reset`);
}

/**
 * Delete the simulation session from the server.
 * Call this when the user is done to free server-side memory.
 */
export async function deleteSimulation(simulationId: string): Promise<void> {
  return request('DELETE', `/api/simulations/${simulationId}`);
}
