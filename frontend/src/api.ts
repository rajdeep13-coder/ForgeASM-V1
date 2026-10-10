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

export interface CopilotCapabilities {
  available: boolean;
  backend: string;
  model_id: string | null;
  installed_models: string[];
  error?: string | null;
  supports_tool_calling: boolean;
  supports_images: boolean;
  supports_json_schema: boolean;
}

export interface CopilotTelemetry {
  id: string;
  session_id: string;
  backend: string;
  model_id: string;
  tokens_in: number;
  tokens_out: number;
  latency_ms: number;
  tokens_per_sec: number;
  bytes_off_device: number;
}

export interface CopilotRunResponse {
  task_id: string;
  status: string;
  iterations?: number;
  attempts?: Array<Record<string, unknown>>;
  final?: Record<string, unknown> | null;
  explanation?: string | null;
  episode_id?: string;
  verdict?: string;
  tokens?: { in: number; out: number };
  latency_ms?: number;
  tool_calls?: Array<Record<string, unknown>>;
  results?: Array<Record<string, unknown>>;
}

export interface CopilotEpisode {
  episode_id: string;
  task_id: string;
  isa: string;
  verdict: string;
  tokens?: { in: number; out: number };
  latency_ms?: number;
  messages?: Array<Record<string, unknown>>;
  tool_calls?: Array<Record<string, unknown>>;
  results?: Array<Record<string, unknown>>;
}

export interface CopilotTranslationResult {
  episode_id: string;
  verdict: string;
  translation?: Record<string, unknown> | null;
  results: Array<Record<string, unknown>>;
}

export interface CopilotMultimodalResponse {
  stage: 'confirm' | 'solved';
  spec?: Record<string, unknown>;
  result?: Record<string, unknown>;
  model?: Record<string, unknown>;
  checker_basis?: string;
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

export async function getCopilotCapabilities(): Promise<CopilotCapabilities> {
  return request<CopilotCapabilities>('GET', '/api/copilot/capabilities');
}

export async function getCopilotTelemetry(): Promise<{ records: CopilotTelemetry[]; error?: string }> {
  return request('GET', '/api/copilot/telemetry');
}

export async function runCopilot(taskId: string, maxIterations = 4): Promise<CopilotRunResponse> {
  return request<CopilotRunResponse>('POST', '/api/copilot/run', {
    task_id: taskId,
    max_iterations: maxIterations,
  });
}

export async function getCopilotEpisodes(): Promise<{ episodes: CopilotEpisode[] }> {
  return request('GET', '/api/copilot/episodes');
}

export async function translateCopilot(
  sourceIsa: string, targetIsa: string, source: string, maxRepairs = 4,
): Promise<CopilotTranslationResult> {
  return request<CopilotTranslationResult>('POST', '/api/copilot/translate', {
    source_isa: sourceIsa, target_isa: targetIsa, source, max_repairs: maxRepairs,
  });
}

export async function transcribeCopilotImage(
  isa: string, imageDataUrl: string,
): Promise<CopilotMultimodalResponse> {
  return request<CopilotMultimodalResponse>('POST', '/api/copilot/multimodal', {
    isa, image_data_url: imageDataUrl,
  });
}

export async function solveCopilotConfirmedSpec(
  isa: string, confirmedSpec: Record<string, unknown>, maxRepairs = 4,
): Promise<CopilotMultimodalResponse> {
  return request<CopilotMultimodalResponse>('POST', '/api/copilot/multimodal', {
    isa, confirmed_spec: confirmedSpec, max_repairs: maxRepairs,
  });
}
