import React, { useState, useEffect, useRef, useCallback } from 'react';
import './App.css';
import {
  assembleCode,
  SimulatorSocket,
  getExamples,
  type ExamplesByISA,
  type SimState,
  type SimUpdate
} from './api';

// ─── Constants ────────────────────────────────────────────────────────────────

const ISAS = [
  { id: 'risc1', label: 'RISC-1 (Stack)' },
  { id: 'risc2', label: 'RISC-2 (Accumulator)' },
  { id: 'risc3', label: 'RISC-3 (Register)' },
  { id: 'cisc',  label: 'CISC' }
];

const ARCHITECTURES = [
  { id: 'neumann', label: 'Von Neumann' },
  { id: 'harvard', label: 'Harvard' }
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

// ─── Helpers ──────────────────────────────────────────────────────────────────

const hex = (val: number, pad = 4) => val.toString(16).padStart(pad, '0').toUpperCase();

function getStatusClass(status: string): string {
  if (status === 'Idle' || status === 'Assembling...') return 'idle';
  if (status === 'Assembled' || status === 'Initialized') return 'assembled';
  if (status === 'Running' || status === 'Stepped') return 'running';
  if (status === 'Halted' || status === 'Completed') return 'halted';
  if (status.toLowerCase().includes('error')) return 'error';
  return 'idle';
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function App() {
  const [code, setCode]               = useState(DEFAULT_CODE);
  const [isa, setIsa]                 = useState('risc1');
  const [architecture, setArch]       = useState('neumann');
  const [allExamples, setAllExamples] = useState<ExamplesByISA>({});
  const [selectedExample, setExample] = useState('');

  const [isAssembling, setAssembling] = useState(false);
  const [assembleError, setError]     = useState<string | null>(null);
  const [binary, setBinary]           = useState<string | null>(null);

  const [simState, setSimState]             = useState<SimState | null>(null);
  const [prevRegs, setPrevRegs]             = useState<Record<string, number>>({});
  const [status, setStatus]                 = useState('Idle');

  const [memAddrStr, setMemAddrStr]   = useState('0000');
  const [rightTab, setRightTab]       = useState<'registers' | 'memory'>('registers');
  const [bottomTab, setBottomTab]     = useState<'console' | 'binary'>('console');
  const [consoleLines, setConsoleLines] = useState<{ text: string; type: string }[]>([
    { text: 'System ready. Load an example or write assembly code.', type: 'info' }
  ]);

  const socketRef  = useRef<SimulatorSocket | null>(null);
  const consoleRef = useRef<HTMLDivElement>(null);
  const editorRef  = useRef<HTMLTextAreaElement>(null);
  const lineNumRef = useRef<HTMLDivElement>(null);

  const currentExamples = allExamples[isa] || [];

  // Auto-scroll console
  useEffect(() => {
    if (consoleRef.current) {
      consoleRef.current.scrollTop = consoleRef.current.scrollHeight;
    }
  }, [consoleLines]);

  // Sync line numbers scroll with editor
  const syncScroll = useCallback(() => {
    if (editorRef.current && lineNumRef.current) {
      lineNumRef.current.scrollTop = editorRef.current.scrollTop;
    }
  }, []);

  // Load examples & connect WebSocket
  useEffect(() => {
    getExamples()
      .then(setAllExamples)
      .catch(err => console.error('Failed to load examples:', err));

    socketRef.current = new SimulatorSocket((update: SimUpdate) => {
      const s = update.status;
      setStatus(
        s === 'initialized' ? 'Initialized' :
        s === 'stepped'     ? 'Stepped'     :
        s === 'completed'   ? 'Halted'      :
        s === 'running'     ? 'Running'     :
        s === 'reset'       ? 'Initialized' :
        s === 'error'       ? 'Error'       :
        s
      );

      if (update.error) {
        setError(update.error);
        addLine(`Simulator error: ${update.error}`, 'error');
      }
      if (update.state) {
        setSimState(prev => {
          if (prev) setPrevRegs(prev.registers);
          return update.state!;
        });
        if (s === 'completed' || (update.state.halted)) {
          addLine('--- Execution halted ---', 'system');
          if (update.state.output) addLine(update.state.output, 'success');
        }
        if (s === 'initialized') {
          addLine(`Simulator initialized [ISA: ${isa.toUpperCase()}, Arch: ${architecture}]`, 'system');
        }
      }
    });

    socketRef.current.connect().catch(err => {
      addLine('WebSocket connection failed. Check backend is running.', 'error');
      console.error(err);
    });

    return () => socketRef.current?.disconnect();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function addLine(text: string, type = 'info') {
    setConsoleLines(prev => [...prev, { text, type }]);
  }

  // ─── Handlers ─────────────────────────────────────────────────────────────

  const handleExampleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const name = e.target.value;
    setExample(name);
    const ex = currentExamples.find(x => x.name === name);
    if (ex) setCode(ex.code);
  };

  const handleIsaChange = (val: string) => {
    setIsa(val);
    setExample('');
  };

  const handleAssemble = async () => {
    setAssembling(true);
    setError(null);
    setBinary(null);
    setSimState(null);
    setPrevRegs({});
    setStatus('Assembling...');
    addLine(`Assembling for ${isa.toUpperCase()}...`, 'system');

    try {
      const res = await assembleCode(code, isa);
      if (res.success) {
        setBinary(res.binary);
        setStatus('Assembled');
        const lineCount = res.binary.trim().split('\n').length;
        addLine(`Assembly successful — ${lineCount} instruction(s) encoded.`, 'success');
        setBottomTab('console');

        if (socketRef.current) {
          socketRef.current.init({ isa, memory_architecture: architecture, binary: res.binary });
        }
      } else {
        const errMsg = res.error || 'Unknown assembly error';
        setError(errMsg);
        setStatus('Error');
        addLine(`Error: ${errMsg}`, 'error');
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Network error';
      setError(msg);
      setStatus('Error');
      addLine(`Network error: ${msg}`, 'error');
    } finally {
      setAssembling(false);
    }
  };

  const handleRun = () => {
    if (!socketRef.current) return;
    socketRef.current.run();
    setStatus('Running');
    addLine('Running program...', 'system');
  };

  const handleStep = () => {
    socketRef.current?.step();
  };

  const handleReset = () => {
    socketRef.current?.reset();
    setPrevRegs({});
    addLine('Processor reset.', 'system');
  };

  // ─── Derived ──────────────────────────────────────────────────────────────

  const lineCount   = code.split('\n').length;
  const lineNumbers = Array.from({ length: Math.max(1, lineCount) }, (_, i) => i + 1).join('\n');
  const memOffset   = parseInt(memAddrStr, 16) || 0;
  const statusClass = getStatusClass(status);
  const isHalted    = simState?.halted ?? false;
  const canSimulate = !!binary && !isHalted;
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

        {/* ISA selector */}
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

        {/* Architecture selector */}
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

        {/* Example selector */}
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

        {/* Status */}
        <div className={`status-badge ${statusClass}`}>
          <span className="dot" />
          {status}
        </div>

        {/* IP indicator */}
        {simState && (
          <div className="ip-badge">
            IP: 0x{hex(simState.ip ?? 0)}
          </div>
        )}
      </header>

      {/* ── Workspace ── */}
      <div className="workspace">

        {/* ── Editor Panel ── */}
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
            <div className="line-numbers" ref={lineNumRef}>
              {lineNumbers}
            </div>
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

          {/* Action bar */}
          <div className="action-bar">
            <button
              className="btn btn-assemble"
              onClick={handleAssemble}
              disabled={isAssembling}
            >
              <IconBuild />
              {isAssembling ? 'Assembling…' : 'Assemble & Load'}
            </button>

            <div className="action-bar-spacer" />

            <button
              className="btn btn-run"
              onClick={handleRun}
              disabled={!canSimulate || status === 'Running'}
              title="Run entire program"
            >
              <IconPlay />
              Run
            </button>
            <button
              className="btn btn-step"
              onClick={handleStep}
              disabled={!canSimulate || status === 'Running'}
              title="Step one instruction"
            >
              <IconStep />
              Step
            </button>
            <button
              className="btn btn-reset"
              onClick={handleReset}
              disabled={!binary}
              title="Reset processor"
            >
              <IconReset />
              Reset
            </button>
          </div>
        </div>

        {/* ── Right Panel ── */}
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

          {/* Registers tab */}
          {rightTab === 'registers' && (
            <div className="panel-section">
              {/* Flags */}
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

              <div className="panel-section-title">
                General Purpose & Special
              </div>

              <div className="registers-scroll">
                {simState ? (
                  Object.entries(simState.registers).map(([name, val]) => {
                    const changed = prevRegs[name] !== undefined && prevRegs[name] !== val;
                    return (
                      <div key={name} className={`register-row ${changed ? 'changed' : ''}`}>
                        <span className="reg-name">{name}</span>
                        <div className="reg-values">
                          <span className="reg-hex">0x{hex(val)}</span>
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

          {/* Memory tab */}
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
                          bytes.push(hex(v, 2));
                          ascii += v >= 32 && v <= 126 ? String.fromCharCode(v) : '·';
                        } else {
                          bytes.push('--');
                          ascii += ' ';
                        }
                      }
                      return (
                        <div key={base} className="memory-row">
                          <span className="mem-addr">{hex(base, 4)}</span>
                          <div className="mem-bytes">
                            {bytes.map((b, i) => (
                              <span key={i} className="mem-byte">{b}</span>
                            ))}
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

      {/* ── Bottom Output ── */}
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
          {bottomTab === 'console' && (
            <>
              {consoleLines.map((line, i) => (
                <span key={i} className={`output-line ${line.type}`}>{line.text}</span>
              ))}
            </>
          )}

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
