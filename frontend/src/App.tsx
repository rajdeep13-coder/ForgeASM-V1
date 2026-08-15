import React, { useState, useEffect, useRef, useCallback } from 'react';
import './App.css';
import {
  assembleCode,
  createSimulation,
  stepSimulation,
  runSimulation,
  resetSimulation,
  deleteSimulation,
  getExamples,
  APIError,
  type ExamplesByISA,
  type SimState,
} from './api';

// ─── Constants ────────────────────────────────────────────────────────────────

const ISAS = [
  { id: 'risc1', label: 'RISC-1 (Stack)' },
  { id: 'risc2', label: 'RISC-2 (Accumulator)' },
  { id: 'risc3', label: 'RISC-3 (Register)' },
  { id: 'cisc',  label: 'CISC' },
];

const ARCHITECTURES = [
  { id: 'neumann', label: 'Von Neumann' },
  { id: 'harvard', label: 'Harvard' },
];

const DEFAULT_CODE = `; ForgeASM — Assembly Editor
; Select an ISA and load an example, or write your own code.
`;

// ─── Icons ────────────────────────────────────────────────────────────────────

const IconCpu = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="4" y="4" width="16" height="16" rx="2"/>
    <rect x="9" y="9" width="6" height="6"/>
    <line x1="9" y1="2" x2="9" y2="4"/><line x1="15" y1="2" x2="15" y2="4"/>
    <line x1="9" y1="20" x2="9" y2="22"/><line x1="15" y1="20" x2="15" y2="22"/>
    <line x1="20" y1="9" x2="22" y2="9"/><line x1="20" y1="15" x2="22" y2="15"/>
    <line x1="2" y1="9" x2="4" y2="9"/><line x1="2" y1="15" x2="4" y2="15"/>
  </svg>
);

const IconPlay = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor">
    <polygon points="5,3 19,12 5,21"/>
  </svg>
);

const IconStep = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="13,17 18,12 13,7"/>
    <line x1="6" y1="12" x2="18" y2="12"/>
  </svg>
);

const IconReset = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="1,4 1,10 7,10"/>
    <path d="M3.51 15a9 9 0 1 0 .49-4"/>
  </svg>
);

const IconBuild = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="16,3 21,8 8,21"/>
    <line x1="12" y1="20" x2="21" y2="9"/>
    <line x1="3" y1="11" x2="8" y2="11"/>
    <line x1="5" y1="9" x2="5" y2="13"/>
  </svg>
);

// ─── Types ────────────────────────────────────────────────────────────────────

type AppStatus =
  | 'idle'
  | 'assembling'
  | 'initializing'
  | 'ready'
  | 'stepping'
  | 'running'
  | 'halted'
  | 'resetting'
  | 'error';

interface ConsoleLine {
  text: string;
  type: 'info' | 'success' | 'error' | 'system';
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

const hexFmt = (val: number, pad = 4) =>
  val.toString(16).padStart(pad, '0').toUpperCase();

function statusLabel(s: AppStatus): string {
  const map: Record<AppStatus, string> = {
    idle: 'Idle',
    assembling: 'Assembling…',
    initializing: 'Initializing…',
    ready: 'Ready',
    stepping: 'Stepping…',
    running: 'Running…',
    halted: 'Halted',
    resetting: 'Resetting…',
    error: 'Error',
  };
  return map[s];
}

function statusClass(s: AppStatus): string {
  if (s === 'idle' || s === 'assembling' || s === 'initializing') return 'idle';
  if (s === 'ready') return 'assembled';
  if (s === 'stepping' || s === 'running' || s === 'resetting') return 'running';
  if (s === 'halted') return 'halted';
  if (s === 'error') return 'error';
  return 'idle';
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function App() {
  // Editor state
  const [code, setCode]               = useState(DEFAULT_CODE);
  const [isa, setIsa]                 = useState('risc1');
  const [architecture, setArch]       = useState('neumann');
  const [allExamples, setAllExamples] = useState<ExamplesByISA>({});
  const [selectedExample, setExample] = useState('');

  // Workflow state
  const [appStatus, setAppStatus] = useState<AppStatus>('idle');
  const [binary, setBinary]       = useState<string | null>(null);
  const [simId, setSimId]         = useState<string | null>(null);
  const [simState, setSimState]   = useState<SimState | null>(null);
  const [prevRegs, setPrevRegs]   = useState<Record<string, number>>({});

  // UI state
  const [rightTab, setRightTab]     = useState<'registers' | 'memory'>('registers');
  const [bottomTab, setBottomTab]   = useState<'console' | 'binary'>('console');
  const [memAddrStr, setMemAddrStr] = useState('0000');
  const [console_, setConsole]      = useState<ConsoleLine[]>([
    { text: 'System ready. Load an example or write assembly code.', type: 'info' },
  ]);

  const consoleRef  = useRef<HTMLDivElement>(null);
  const editorRef   = useRef<HTMLTextAreaElement>(null);
  const lineNumRef  = useRef<HTMLDivElement>(null);
  // Keep a ref to the current simId for the cleanup effect
  const simIdRef    = useRef<string | null>(null);

  // Keep simIdRef in sync
  useEffect(() => { simIdRef.current = simId; }, [simId]);

  const currentExamples = allExamples[isa] || [];

  // ── Load examples on mount ─────────────────────────────────────────────────
  useEffect(() => {
    getExamples()
      .then(setAllExamples)
      .catch(() => addLine('Could not load examples from server.', 'error'));

    // Clean up simulation when the component unmounts / tab closes
    return () => {
      if (simIdRef.current) {
        deleteSimulation(simIdRef.current).catch(() => {/* best-effort */});
      }
    };
  }, []);

  // ── Auto-scroll console ────────────────────────────────────────────────────
  useEffect(() => {
    if (consoleRef.current) {
      consoleRef.current.scrollTop = consoleRef.current.scrollHeight;
    }
  }, [console_]);

  // ── Sync line numbers ──────────────────────────────────────────────────────
  const syncScroll = useCallback(() => {
    if (editorRef.current && lineNumRef.current) {
      lineNumRef.current.scrollTop = editorRef.current.scrollTop;
    }
  }, []);

  // ── Helpers ───────────────────────────────────────────────────────────────

  function addLine(text: string, type: ConsoleLine['type'] = 'info') {
    setConsole(prev => [...prev, { text, type }]);
  }

  function applyState(newState: SimState) {
    setSimState(prev => {
      if (prev) setPrevRegs(prev.registers);
      return newState;
    });
    if (newState.halted) setAppStatus('halted');
  }

  // ── Assemble & Load ───────────────────────────────────────────────────────

  const handleAssemble = async () => {
    if (appStatus === 'assembling' || appStatus === 'initializing') return;

    // Delete any previous session
    if (simId) {
      deleteSimulation(simId).catch(() => {/* best-effort */});
      setSimId(null);
      simIdRef.current = null;
    }

    setAppStatus('assembling');
    setBinary(null);
    setSimState(null);
    setPrevRegs({});
    addLine(`Assembling [ISA: ${isa.toUpperCase()}]…`, 'system');

    let assembledBinary: string;
    try {
      const res = await assembleCode(code, isa);
      if (!res.success) {
        addLine(`Assembly error: ${res.error}`, 'error');
        setAppStatus('error');
        return;
      }
      assembledBinary = res.binary;
      const lineCount = assembledBinary.trim().split('\n').length;
      addLine(`Assembly OK — ${lineCount} instruction(s) encoded.`, 'success');
      setBinary(assembledBinary);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      addLine(`Network error during assembly: ${msg}`, 'error');
      setAppStatus('error');
      return;
    }

    // ── Initialize simulation ────────────────────────────────────────────────
    setAppStatus('initializing');
    addLine(`Initializing simulator [Memory: ${architecture}]…`, 'system');

    try {
      const session = await createSimulation(isa, architecture, assembledBinary);
      setSimId(session.simulation_id);
      simIdRef.current = session.simulation_id;
      applyState(session.state);
      setAppStatus('ready');
      addLine(`Simulation ready (id: ${session.simulation_id.slice(0, 8)}…)`, 'success');
    } catch (err) {
      const msg = err instanceof APIError ? err.message : String(err);
      addLine(`Simulation init failed: ${msg}`, 'error');
      setAppStatus('error');
    }
  };

  // ── Step ──────────────────────────────────────────────────────────────────

  const handleStep = async () => {
    if (!simId || appStatus === 'stepping' || appStatus === 'running') return;
    setAppStatus('stepping');
    try {
      const res = await stepSimulation(simId);
      applyState(res.state);
      if (res.last_instruction) {
        addLine(`→ ${res.last_instruction}  (PC: 0x${hexFmt(res.state.pc)})`, 'info');
      }
      if (!res.state.halted) setAppStatus('ready');
    } catch (err) {
      const msg = err instanceof APIError ? err.message : String(err);
      addLine(`Step error: ${msg}`, 'error');
      setAppStatus('error');
    }
  };

  // ── Run ───────────────────────────────────────────────────────────────────

  const handleRun = async () => {
    if (!simId || appStatus === 'running') return;
    setAppStatus('running');
    addLine('Running program…', 'system');
    try {
      const res = await runSimulation(simId, 10000);
      applyState(res.state);
      addLine(
        `Run complete — ${res.cycles_executed} cycles, reason: ${res.halt_reason}`,
        res.halt_reason === 'halted' ? 'success' : 'info',
      );
      if (res.state.output) addLine(res.state.output, 'success');
    } catch (err) {
      const msg = err instanceof APIError ? err.message : String(err);
      addLine(`Run error: ${msg}`, 'error');
      setAppStatus('error');
    }
  };

  // ── Reset ─────────────────────────────────────────────────────────────────

  const handleReset = async () => {
    if (!simId) return;
    setAppStatus('resetting');
    setPrevRegs({});
    try {
      const res = await resetSimulation(simId);
      applyState(res.state);
      setAppStatus('ready');
      addLine('Processor reset.', 'system');
    } catch (err) {
      const msg = err instanceof APIError ? err.message : String(err);
      addLine(`Reset error: ${msg}`, 'error');
      setAppStatus('error');
    }
  };

  // ── ISA change ────────────────────────────────────────────────────────────

  const handleIsaChange = (val: string) => {
    setIsa(val);
    setExample('');
  };

  const handleExampleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const name = e.target.value;
    setExample(name);
    const ex = currentExamples.find(x => x.name === name);
    if (ex) setCode(ex.code);
  };

  // ─── Derived ──────────────────────────────────────────────────────────────

  const lineCount   = code.split('\n').length;
  const lineNumbers = Array.from({ length: Math.max(1, lineCount) }, (_, i) => i + 1).join('\n');
  const memOffset   = parseInt(memAddrStr, 16) || 0;
  const isHalted    = simState?.halted ?? false;
  const busy        = appStatus === 'assembling' || appStatus === 'initializing' ||
                      appStatus === 'stepping'   || appStatus === 'running' ||
                      appStatus === 'resetting';
  const canStep     = !!simId && !isHalted && !busy;
  const canRun      = !!simId && !isHalted && appStatus !== 'running';
  const canReset    = !!simId && !busy;
  const binaryLines = binary ? binary.trim().split('\n') : [];

  // ─── Render ───────────────────────────────────────────────────────────────

  return (
    <div className="app">

      {/* ── Topbar ── */}
      <header className="topbar">
        <div className="topbar-brand">
          <IconCpu />
          <span className="topbar-brand-name">ForgeASM</span>
        </div>

        <div className="topbar-divider" />

        <div className="topbar-select-group">
          <label htmlFor="isa-select">ISA</label>
          <select
            id="isa-select"
            className="topbar-select"
            value={isa}
            onChange={e => handleIsaChange(e.target.value)}
          >
            {ISAS.map(i => (
              <option key={i.id} value={i.id}>{i.label}</option>
            ))}
          </select>
        </div>

        <div className="topbar-select-group">
          <label htmlFor="arch-select">Memory</label>
          <select
            id="arch-select"
            className="topbar-select"
            value={architecture}
            onChange={e => setArch(e.target.value)}
          >
            {ARCHITECTURES.map(a => (
              <option key={a.id} value={a.id}>{a.label}</option>
            ))}
          </select>
        </div>

        {currentExamples.length > 0 && (
          <div className="topbar-select-group">
            <label htmlFor="example-select">Example</label>
            <select
              id="example-select"
              className="topbar-select"
              value={selectedExample}
              onChange={handleExampleChange}
            >
              <option value="">— Select —</option>
              {currentExamples.map(ex => (
                <option key={ex.name} value={ex.name}>{ex.name}</option>
              ))}
            </select>
          </div>
        )}

        <div className="topbar-spacer" />

        <div className={`status-badge ${statusClass(appStatus)}`}>
          <span className="dot" />
          {statusLabel(appStatus)}
        </div>

        {simState && (
          <div className="ip-badge">
            IP: 0x{hexFmt(simState.pc ?? 0)}
          </div>
        )}

        {simState && (
          <div className="ip-badge" style={{ color: 'var(--blue)', borderColor: 'rgba(91,155,255,0.2)', background: 'var(--blue-dim)' }}>
            {simState.cycle_count} cycles
          </div>
        )}
      </header>

      {/* ── Workspace ── */}
      <div className="workspace">

        {/* ── Editor ── */}
        <div className="editor-panel">
          <div className="editor-toolbar">
            <div className="editor-tab active">
              <span className="editor-tab-dot" />
              main.asm
            </div>
            <div className="toolbar-spacer" />
            <span style={{ fontSize: '12px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
              {lineCount} lines
            </span>
          </div>

          <div className="editor-body">
            <div className="line-numbers" ref={lineNumRef}>{lineNumbers}</div>
            <textarea
              ref={editorRef}
              className="code-editor"
              value={code}
              onChange={e => setCode(e.target.value)}
              onScroll={syncScroll}
              spellCheck={false}
              autoComplete="off"
              autoCorrect="off"
              autoCapitalize="off"
              aria-label="Assembly code editor"
            />
          </div>

          <div className="action-bar">
            <button
              className="btn btn-assemble"
              onClick={handleAssemble}
              disabled={busy}
            >
              <IconBuild />
              {appStatus === 'assembling' ? 'Assembling…' : appStatus === 'initializing' ? 'Loading…' : 'Assemble & Load'}
            </button>

            <div className="action-bar-spacer" />

            <button className="btn btn-run"  onClick={handleRun}   disabled={!canRun}  title="Run all instructions">
              <IconPlay /> Run
            </button>
            <button className="btn btn-step" onClick={handleStep}  disabled={!canStep} title="Step one instruction">
              <IconStep /> Step
            </button>
            <button className="btn btn-reset" onClick={handleReset} disabled={!canReset} title="Reset CPU">
              <IconReset /> Reset
            </button>
          </div>
        </div>

        {/* ── Right panel ── */}
        <div className="right-panel">
          <div className="panel-tabs">
            <button
              className={`panel-tab ${rightTab === 'registers' ? 'active' : ''}`}
              onClick={() => setRightTab('registers')}
            >
              Registers
            </button>
            <button
              className={`panel-tab ${rightTab === 'memory' ? 'active' : ''}`}
              onClick={() => setRightTab('memory')}
            >
              Memory
            </button>
          </div>

          {/* Registers */}
          {rightTab === 'registers' && (
            <div className="panel-section">
              <div className="flags-row">
                {(['Z', 'C', 'O', 'N'] as const).map(f => {
                  const active = simState?.flags?.[f] ?? false;
                  return (
                    <div key={f} className={`flag-chip ${active ? 'active' : ''}`}>
                      <span className="flag-chip-label">{f}</span>
                      <span className="flag-chip-value">{active ? '1' : '0'}</span>
                    </div>
                  );
                })}
              </div>
              <div className="panel-section-title">General Purpose & Special</div>
              <div className="registers-scroll">
                {simState ? (
                  Object.entries(simState.registers).map(([name, val]) => {
                    const changed = prevRegs[name] !== undefined && prevRegs[name] !== val;
                    return (
                      <div key={name} className={`register-row ${changed ? 'changed' : ''}`}>
                        <span className="reg-name">{name}</span>
                        <div className="reg-values">
                          <span className="reg-hex">0x{hexFmt(val)}</span>
                          <span className="reg-dec">{val}</span>
                        </div>
                      </div>
                    );
                  })
                ) : (
                  <div className="registers-empty">
                    Assemble code to initialize<br />the processor state.
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Memory */}
          {rightTab === 'memory' && (
            <div className="panel-section">
              <div className="memory-panel">
                <div className="memory-addr-bar">
                  <span>0x</span>
                  <input
                    className="memory-addr-input"
                    type="text"
                    value={memAddrStr}
                    onChange={e =>
                      setMemAddrStr(
                        e.target.value.replace(/[^0-9a-fA-F]/g, '').slice(0, 4).toUpperCase()
                      )
                    }
                    placeholder="0000"
                    maxLength={4}
                    aria-label="Memory address offset"
                  />
                  <span style={{ color: 'var(--text-muted)', fontSize: '11px' }}>base</span>
                </div>
                <div className="memory-scroll">
                  {simState?.memory ? (
                    Array.from({ length: 16 }).map((_, row) => {
                      const base = memOffset + row * 8;
                      if (base >= simState.memory.length) return null;
                      let ascii = '';
                      const bytes: string[] = [];
                      for (let i = 0; i < 8; i++) {
                        const addr = base + i;
                        if (addr < simState.memory.length) {
                          const v = simState.memory[addr];
                          bytes.push(hexFmt(v, 2));
                          ascii += v >= 32 && v <= 126 ? String.fromCharCode(v) : '·';
                        } else {
                          bytes.push('--');
                          ascii += ' ';
                        }
                      }
                      return (
                        <div key={base} className="memory-row">
                          <span className="mem-addr">{hexFmt(base, 4)}</span>
                          <div className="mem-bytes">
                            {bytes.map((b, i) => <span key={i} className="mem-byte">{b}</span>)}
                          </div>
                          <span className="mem-ascii">{ascii}</span>
                        </div>
                      );
                    })
                  ) : (
                    <div className="placeholder">
                      <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                        <rect x="2" y="3" width="20" height="14" rx="2"/>
                        <line x1="8" y1="21" x2="16" y2="21"/>
                        <line x1="12" y1="17" x2="12" y2="21"/>
                      </svg>
                      Memory not initialized
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ── Bottom output ── */}
      <div className="output-area">
        <div className="output-tabs">
          <button
            className={`output-tab ${bottomTab === 'console' ? 'active' : ''}`}
            onClick={() => setBottomTab('console')}
          >
            Console
          </button>
          <button
            className={`output-tab ${bottomTab === 'binary' ? 'active' : ''}`}
            onClick={() => setBottomTab('binary')}
          >
            Binary
          </button>
        </div>

        <div className="output-content" ref={consoleRef}>
          {bottomTab === 'console' && console_.map((line, i) => (
            <span key={i} className={`output-line ${line.type}`}>{line.text}</span>
          ))}

          {bottomTab === 'binary' && (
            binary ? (
              <div className="binary-output">
                {binaryLines.map((bits, i) => (
                  <div key={i} className="binary-row">
                    <span className="binary-index">{i.toString().padStart(3, '0')}</span>
                    <span className="binary-bits">{bits}</span>
                  </div>
                ))}
              </div>
            ) : (
              <span className="output-line info">No binary output yet. Assemble code first.</span>
            )
          )}
        </div>
      </div>
    </div>
  );
}
