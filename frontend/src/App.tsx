import { useState, useEffect, useRef, useCallback } from 'react';
import './App.css';
import {
  assembleCode, createSimulation, stepSimulation,
  runSimulation, resetSimulation, deleteSimulation,
  getExamples, APIError,
  type ExamplesByISA, type SimState,
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
; Select an ISA above and load an example, or write your own code.
`;

// ─── Types ────────────────────────────────────────────────────────────────────

type AppStatus = 'idle' | 'assembling' | 'initializing' | 'ready' | 'stepping' | 'running' | 'halted' | 'resetting' | 'error';

interface TraceEntry {
  cycle: number;
  pc: number;
  instruction: string;
  regChanges: Array<{ name: string; from: number; to: number }>;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

const h = (v: number, pad = 4) => v.toString(16).padStart(pad, '0').toUpperCase();

function diffRegisters(prev: Record<string, number>, next: Record<string, number>): Array<{ name: string; from: number; to: number }> {
  return Object.entries(next)
    .filter(([k, v]) => prev[k] !== undefined && prev[k] !== v)
    .map(([k, v]) => ({ name: k, from: prev[k], to: v }));
}

// ─── Icons ────────────────────────────────────────────────────────────────────

const IcCpu = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/>
    <line x1="9" y1="2" x2="9" y2="4"/><line x1="15" y1="2" x2="15" y2="4"/>
    <line x1="9" y1="20" x2="9" y2="22"/><line x1="15" y1="20" x2="15" y2="22"/>
    <line x1="20" y1="9" x2="22" y2="9"/><line x1="20" y1="15" x2="22" y2="15"/>
    <line x1="2" y1="9" x2="4" y2="9"/><line x1="2" y1="15" x2="4" y2="15"/>
  </svg>
);
const IcPlay    = () => <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="5,3 19,12 5,21"/></svg>;
const IcStep    = () => <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="13,17 18,12 13,7"/><line x1="6" y1="12" x2="18" y2="12"/></svg>;
const IcReset   = () => <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="1,4 1,10 7,10"/><path d="M3.51 15a9 9 0 1 0 .49-4"/></svg>;
const IcBuild   = () => <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>;
const IcTrash   = () => <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="3,6 5,6 21,6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4h6v2"/></svg>;

// ─── Status helpers ───────────────────────────────────────────────────────────

function statusLabel(s: AppStatus) {
  return { idle:'Idle', assembling:'Assembling…', initializing:'Initializing…', ready:'Ready',
           stepping:'Stepping…', running:'Running…', halted:'Halted', resetting:'Resetting…', error:'Error' }[s];
}
function statusCls(s: AppStatus) {
  if (s === 'halted') return 'halted';
  if (s === 'error') return 'error';
  if (s === 'ready') return 'ready';
  if (s === 'running' || s === 'stepping' || s === 'resetting') return 'running';
  return 'idle';
}

// ─── Sub-components ───────────────────────────────────────────────────────────

/** CPU state summary card shown at top of right panel */
function CpuStatusCard({ isa, arch, state, appStatus }: {
  isa: string; arch: string; state: SimState | null; appStatus: AppStatus;
}) {
  const sc = statusCls(appStatus);
  return (
    <div className="cpu-card">
      <div className="cpu-card-header">
        <IcCpu />
        <span>CPU STATE</span>
        <div className={`cpu-status-dot ${sc}`} />
        <span className={`cpu-status-text ${sc}`}>{statusLabel(appStatus).toUpperCase()}</span>
      </div>
      <div className="cpu-card-meta">
        <span className="cpu-meta-item"><span className="cpu-meta-label">ISA</span><span className="cpu-meta-val">{isa.toUpperCase()}</span></span>
        <span className="cpu-card-sep"/>
        <span className="cpu-meta-item"><span className="cpu-meta-label">MEM</span><span className="cpu-meta-val">{arch === 'harvard' ? 'Harvard' : 'Von Neumann'}</span></span>
      </div>
      {state && (
        <div className="cpu-card-kpis">
          <div className="kpi">
            <span className="kpi-label">PC</span>
            <span className="kpi-val mono">0x{h(state.pc)}</span>
            <span className="kpi-sub">{state.pc}</span>
          </div>
          <div className="kpi">
            <span className="kpi-label">Cycles</span>
            <span className="kpi-val mono">{state.cycle_count}</span>
          </div>
          <div className="kpi">
            <span className="kpi-label">Next</span>
            <span className="kpi-val mono instr">{state.current_instruction ?? (state.halted ? 'HALTED' : '—')}</span>
          </div>
        </div>
      )}
    </div>
  );
}

/** Dynamic flags panel — reads whatever flags the backend returns */
function FlagsPanel({ flags }: { flags: Record<string, boolean> }) {
  const entries = Object.entries(flags);
  if (entries.length === 0) {
    return <div className="flags-empty">No flags exposed by this ISA</div>;
  }
  return (
    <div className="flags-grid">
      {entries.map(([name, val]) => (
        <div key={name} className={`flag-chip ${val ? 'active' : ''}`}>
          <span className="flag-name">{name}</span>
          <span className="flag-val">{val ? '1' : '0'}</span>
        </div>
      ))}
    </div>
  );
}

/** Dynamic registers panel — renders whatever the backend returns */
function RegistersPanel({ registers, prev }: { registers: Record<string, number>; prev: Record<string, number> }) {
  const entries = Object.entries(registers);
  if (entries.length === 0) return <div className="reg-empty">No registers</div>;
  return (
    <div className="reg-list">
      {entries.map(([name, val]) => {
        const changed = prev[name] !== undefined && prev[name] !== val;
        return (
          <div key={name} className={`reg-row ${changed ? 'changed' : ''}`}>
            <span className="reg-name">{name}</span>
            <div className="reg-vals">
              <span className="reg-hex">0x{h(val)}</span>
              <span className="reg-dec">{val}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

/** Execution trace */
function TracePanel({ trace, onClear }: { trace: TraceEntry[]; onClear: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [trace]);

  if (trace.length === 0) {
    return (
      <div className="trace-empty">
        Step through the program to build an execution trace.
      </div>
    );
  }
  return (
    <div className="trace-wrap">
      <div className="trace-toolbar">
        <span className="trace-count">{trace.length} entries</span>
        <button className="trace-clear-btn" onClick={onClear} title="Clear trace">
          <IcTrash /> Clear
        </button>
      </div>
      <div className="trace-list" ref={ref}>
        {trace.map((e, i) => (
          <div key={i} className="trace-entry">
            <div className="trace-header">
              <span className="trace-cycle">#{e.cycle}</span>
              <span className="trace-pc">PC: 0x{h(e.pc)}</span>
              <span className="trace-instr">{e.instruction}</span>
            </div>
            {e.regChanges.length > 0 && (
              <div className="trace-changes">
                {e.regChanges.map(c => (
                  <span key={c.name} className="trace-change">
                    {c.name}: 0x{h(c.from)} → 0x{h(c.to)}
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

/** Memory hex viewer */
function MemoryPanel({ memory, pc, memAddrStr, onAddrChange }: {
  memory: number[] | null; pc: number; memAddrStr: string; onAddrChange: (s: string) => void;
}) {
  const offset = parseInt(memAddrStr, 16) || 0;
  // Button to jump to PC
  const jumpToPC = () => {
    const aligned = Math.max(0, Math.floor(pc / 8) * 8);
    onAddrChange(aligned.toString(16).padStart(4, '0').toUpperCase());
  };

  return (
    <div className="mem-panel">
      <div className="mem-toolbar">
        <span className="mem-label">0x</span>
        <input
          className="mem-addr-input"
          value={memAddrStr}
          onChange={e => onAddrChange(e.target.value.replace(/[^0-9a-fA-F]/g, '').slice(0,4).toUpperCase())}
          maxLength={4}
          placeholder="0000"
        />
        <button className="mem-jump-btn" onClick={jumpToPC} title="Jump to PC" disabled={!memory}>
          → PC
        </button>
      </div>
      <div className="mem-header-row">
        <span className="mem-addr-col">ADDR</span>
        <span className="mem-bytes-col">+0 +1 +2 +3 +4 +5 +6 +7</span>
        <span className="mem-ascii-col">ASCII</span>
      </div>
      <div className="mem-rows">
        {memory ? (
          Array.from({ length: 16 }, (_, row) => {
            const base = offset + row * 8;
            if (base >= memory.length) return null;
            let ascii = '';
            const bytes: string[] = [];
            for (let i = 0; i < 8; i++) {
              const addr = base + i;
              if (addr < memory.length) {
                const v = memory[addr];
                bytes.push(h(v, 2));
                ascii += v >= 32 && v <= 126 ? String.fromCharCode(v) : '·';
              } else {
                bytes.push('--');
                ascii += ' ';
              }
            }
            const isPC = pc >= base && pc < base + 8;
            return (
              <div key={base} className={`mem-row ${isPC ? 'pc-row' : ''}`}>
                <span className="mem-addr-col">{h(base, 4)}</span>
                <div className="mem-bytes-col">
                  {bytes.map((b, i) => {
                    const addr = base + i;
                    return <span key={i} className={`mem-byte ${addr === pc ? 'pc-byte' : ''}`}>{b}</span>;
                  })}
                </div>
                <span className="mem-ascii-col">{ascii}</span>
              </div>
            );
          })
        ) : (
          <div className="mem-empty">No memory — assemble and initialize first.</div>
        )}
      </div>
    </div>
  );
}

/** Machine code view with current-PC highlight */
function BinaryPanel({ binary, pc, isaName }: { binary: string | null; pc: number; isaName: string }) {
  const pcRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    pcRef.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }, [pc]);

  if (!binary) return (
    <div className="bin-empty">No binary — assemble first.</div>
  );

  // Each line is one encoded instruction word (CISC may have 2-3 lines per logical instr)
  const lines = binary.trim().split('\n');

  return (
    <div className="bin-list">
      <div className="bin-header">
        <span className="bin-idx-col">IDX</span>
        <span className="bin-bits-col">BITS</span>
      </div>
      {lines.map((bits, i) => {
        const isPC = i === pc;
        return (
          <div key={i} ref={isPC ? pcRef : undefined} className={`bin-row ${isPC ? 'active' : ''}`}>
            <span className="bin-idx-col">{i.toString().padStart(3, '0')}</span>
            <span className="bin-bits-col">{bits}</span>
            {isPC && <span className="bin-arrow">◀ PC</span>}
          </div>
        );
      })}
    </div>
  );
}

/** Program output panel */
function OutputPanel({ output }: { output: string }) {
  return (
    <div className="out-panel">
      {output ? (
        <pre className="out-text">{output}</pre>
      ) : (
        <span className="out-empty">No output yet. Run a program that uses OUT instructions.</span>
      )}
    </div>
  );
}

// ─── Main App ─────────────────────────────────────────────────────────────────

export default function App() {
  // Config
  const [code, setCode]         = useState(DEFAULT_CODE);
  const [isa, setIsa]           = useState('risc1');
  const [arch, setArch]         = useState('neumann');
  const [allExamples, setExamples] = useState<ExamplesByISA>({});
  const [selExample, setSelExample] = useState('');

  // Simulation
  const [appStatus, setStatus]  = useState<AppStatus>('idle');
  const [binary, setBinary]     = useState<string | null>(null);
  const [simId, setSimId]       = useState<string | null>(null);
  const [simState, setSimState] = useState<SimState | null>(null);
  const [prevRegs, setPrevRegs] = useState<Record<string, number>>({});

  // Debugger extras
  const [trace, setTrace]       = useState<TraceEntry[]>([]);
  const [lastRun, setLastRun]   = useState<{ cycles: number; reason: string } | null>(null);
  const [assembleErr, setAsmErr]= useState<string | null>(null);

  // Panel tabs
  const [rightTab, setRightTab] = useState<'state' | 'memory' | 'trace' | 'output'>('state');
  const [bottomTab, setBotTab]  = useState<'console' | 'binary'>('console');
  const [memAddrStr, setMemAddr]= useState('0000');

  // Editor refs
  const editorRef   = useRef<HTMLTextAreaElement>(null);
  const lineNumRef  = useRef<HTMLDivElement>(null);
  const simIdRef    = useRef<string | null>(null);
  const consoleRef  = useRef<HTMLDivElement>(null);

  // Console log
  const [consoleLines, setConLines] = useState<Array<{ t: string; cls: string }>>([
    { t: 'System ready. Load an example or write assembly code.', cls: 'info' },
  ]);

  const log = useCallback((t: string, cls = 'info') => {
    setConLines(p => [...p, { t, cls }]);
  }, []);

  useEffect(() => { simIdRef.current = simId; }, [simId]);
  useEffect(() => {
    if (consoleRef.current) consoleRef.current.scrollTop = consoleRef.current.scrollHeight;
  }, [consoleLines]);

  const syncScroll = useCallback(() => {
    if (editorRef.current && lineNumRef.current)
      lineNumRef.current.scrollTop = editorRef.current.scrollTop;
  }, []);

  // Load examples
  useEffect(() => {
    getExamples().then(setExamples).catch(() => log('Could not load examples.', 'error'));
    return () => {
      if (simIdRef.current) deleteSimulation(simIdRef.current).catch(() => {});
    };
  }, []);

  const currentExamples = allExamples[isa] || [];

  // ── apply state helper ────────────────────────────────────────────────────

  function applyState(ns: SimState) {
    setSimState(prev => {
      if (prev) setPrevRegs(prev.registers);
      return ns;
    });
    if (ns.halted) setStatus('halted');
  }

  // ── Assemble & Load ───────────────────────────────────────────────────────

  const handleAssemble = async () => {
    if (appStatus === 'assembling' || appStatus === 'initializing') return;
    if (simId) { deleteSimulation(simId).catch(() => {}); setSimId(null); simIdRef.current = null; }

    setStatus('assembling');
    setBinary(null); setSimState(null); setPrevRegs({}); setTrace([]); setLastRun(null); setAsmErr(null);
    log(`Assembling [${isa.toUpperCase()}]…`, 'system');

    let bin: string;
    try {
      const res = await assembleCode(code, isa);
      if (!res.success) {
        setAsmErr(res.error ?? 'Assembly failed');
        log(`Assembly error: ${res.error}`, 'error');
        setStatus('error');
        return;
      }
      bin = res.binary;
      setBinary(bin);
      log(`Assembly OK — ${bin.trim().split('\n').length} words encoded.`, 'success');
    } catch (e) {
      const m = e instanceof Error ? e.message : String(e);
      setAsmErr(m);
      log(`Network error: ${m}`, 'error');
      setStatus('error');
      return;
    }

    setStatus('initializing');
    log(`Initializing [Memory: ${arch}]…`, 'system');
    try {
      const sess = await createSimulation(isa, arch, bin);
      setSimId(sess.simulation_id); simIdRef.current = sess.simulation_id;
      applyState(sess.state);
      setStatus('ready');
      log(`Ready (id: ${sess.simulation_id.slice(0, 8)}…)`, 'success');
      setRightTab('state');
    } catch (e) {
      const m = e instanceof APIError ? e.message : String(e);
      log(`Init failed: ${m}`, 'error');
      setStatus('error');
    }
  };

  // ── Step ─────────────────────────────────────────────────────────────────

  const handleStep = async () => {
    if (!simId || appStatus === 'stepping' || appStatus === 'running') return;
    setStatus('stepping');
    try {
      const prevState = simState;
      const res = await stepSimulation(simId);
      // Build trace entry using the instruction that was just executed
      if (res.last_instruction && prevState) {
        const changes = diffRegisters(prevState.registers, res.state.registers);
        setTrace(t => [...t, {
          cycle: res.state.cycle_count,
          pc: prevState.pc,
          instruction: res.last_instruction!,
          regChanges: changes,
        }]);
      }
      applyState(res.state);
      if (!res.state.halted) setStatus('ready');
    } catch (e) {
      const m = e instanceof APIError ? e.message : String(e);
      log(`Step error: ${m}`, 'error');
      setStatus('error');
    }
  };

  // ── Run ──────────────────────────────────────────────────────────────────

  const handleRun = async () => {
    if (!simId || appStatus === 'running') return;
    setStatus('running');
    log('Running…', 'system');
    try {
      const res = await runSimulation(simId, 10000);
      applyState(res.state);
      setLastRun({ cycles: res.cycles_executed, reason: res.halt_reason });
      log(`Done — ${res.cycles_executed} cycles (${res.halt_reason}).`, res.halt_reason === 'halted' ? 'success' : 'info');
      if (res.state.output) log(`Output: ${res.state.output}`, 'output');
      setRightTab('state');
    } catch (e) {
      const m = e instanceof APIError ? e.message : String(e);
      log(`Run error: ${m}`, 'error');
      setStatus('error');
    }
  };

  // ── Reset ────────────────────────────────────────────────────────────────

  const handleReset = async () => {
    if (!simId) return;
    setStatus('resetting');
    setPrevRegs({}); setTrace([]); setLastRun(null);
    try {
      const res = await resetSimulation(simId);
      applyState(res.state);
      setStatus('ready');
      log('Processor reset.', 'system');
    } catch (e) {
      const m = e instanceof APIError ? e.message : String(e);
      log(`Reset error: ${m}`, 'error');
      setStatus('error');
    }
  };

  // ── Derived ──────────────────────────────────────────────────────────────

  const lineCount   = code.split('\n').length;
  const lineNumbers = Array.from({ length: Math.max(1, lineCount) }, (_, i) => i + 1).join('\n');
  const isHalted    = simState?.halted ?? false;
  const busy        = ['assembling','initializing','stepping','running','resetting'].includes(appStatus);
  const canStep     = !!simId && !isHalted && !busy;
  const canRun      = !!simId && !isHalted && appStatus !== 'running';
  const canReset    = !!simId && !busy;

  // ─── Render ───────────────────────────────────────────────────────────────

  return (
    <div className="app">

      {/* ─── Topbar ─── */}
      <header className="topbar">
        <div className="topbar-brand">
          <IcCpu />
          <span className="topbar-brand-name">ForgeASM</span>
          <span className="topbar-brand-sub">Hardware Simulator</span>
        </div>
        <div className="topbar-divider" />

        <div className="tsel-group">
          <label htmlFor="isa-sel">ISA</label>
          <select id="isa-sel" className="tsel" value={isa} onChange={e => { setIsa(e.target.value); setSelExample(''); }}>
            {ISAS.map(i => <option key={i.id} value={i.id}>{i.label}</option>)}
          </select>
        </div>

        <div className="tsel-group">
          <label htmlFor="arch-sel">Memory</label>
          <select id="arch-sel" className="tsel" value={arch} onChange={e => setArch(e.target.value)}>
            {ARCHITECTURES.map(a => <option key={a.id} value={a.id}>{a.label}</option>)}
          </select>
        </div>

        {currentExamples.length > 0 && (
          <div className="tsel-group">
            <label htmlFor="ex-sel">Example</label>
            <select id="ex-sel" className="tsel" value={selExample}
              onChange={e => { setSelExample(e.target.value); const ex = currentExamples.find(x => x.name === e.target.value); if (ex) setCode(ex.code); }}>
              <option value="">— Select —</option>
              {currentExamples.map(ex => <option key={ex.name} value={ex.name}>{ex.name}</option>)}
            </select>
          </div>
        )}

        <div className="topbar-spacer" />

        {/* Status pill */}
        <div className={`status-pill ${statusCls(appStatus)}`}>
          <span className="status-dot" />
          {statusLabel(appStatus)}
        </div>

        {/* Quick KPIs */}
        {simState && <>
          <div className="topbar-kpi">
            <span className="topbar-kpi-label">PC</span>
            <span className="topbar-kpi-val">0x{h(simState.pc)}</span>
          </div>
          <div className="topbar-kpi">
            <span className="topbar-kpi-label">Cycles</span>
            <span className="topbar-kpi-val">{simState.cycle_count}</span>
          </div>
        </>}
      </header>

      {/* ─── Main workspace ─── */}
      <div className="workspace">

        {/* ─── Editor column ─── */}
        <div className="editor-col">
          <div className="editor-titlebar">
            <span className="editor-filename">main.asm</span>
            <span className="editor-linecount">{lineCount} lines</span>
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

          {/* Assembly error banner */}
          {assembleErr && (
            <div className="asm-error-banner">
              <strong>Assembly Error</strong>
              <pre className="asm-error-text">{assembleErr}</pre>
            </div>
          )}

          {/* Action bar */}
          <div className="action-bar">
            <button className="btn btn-assemble" onClick={handleAssemble} disabled={busy}>
              <IcBuild />
              {appStatus === 'assembling' ? 'Assembling…' : appStatus === 'initializing' ? 'Loading…' : 'Assemble & Load'}
            </button>
            <div className="ab-sep" />
            <button className="btn btn-run"   onClick={handleRun}   disabled={!canRun}  title="Run all"><IcPlay  /> Run</button>
            <button className="btn btn-step"  onClick={handleStep}  disabled={!canStep} title="Step one"><IcStep  /> Step</button>
            <button className="btn btn-reset" onClick={handleReset} disabled={!canReset} title="Reset"><IcReset /> Reset</button>
          </div>
        </div>

        {/* ─── Right panel ─── */}
        <div className="right-panel">

          {/* Tab bar */}
          <div className="rp-tabs">
            {(['state','memory','trace','output'] as const).map(t => (
              <button key={t} className={`rp-tab ${rightTab === t ? 'active' : ''}`} onClick={() => setRightTab(t)}>
                {t === 'state' ? 'CPU' : t === 'trace' ? 'Trace' : t === 'output' ? 'Output' : 'Memory'}
                {t === 'trace' && trace.length > 0 && <span className="rp-tab-badge">{trace.length}</span>}
              </button>
            ))}
          </div>

          {/* ── CPU State tab ── */}
          {rightTab === 'state' && (
            <div className="rp-body">
              <CpuStatusCard isa={isa} arch={arch} state={simState} appStatus={appStatus} />

              {lastRun && (
                <div className="run-summary">
                  <span className="rs-label">Last run</span>
                  <span className="rs-val">{lastRun.cycles} cycles</span>
                  <span className={`rs-reason ${lastRun.reason}`}>{lastRun.reason}</span>
                </div>
              )}

              <div className="rp-section-title">Flags</div>
              {simState
                ? <FlagsPanel flags={simState.flags} />
                : <div className="rp-placeholder">Flags will appear after initialization.</div>}

              <div className="rp-section-title">Registers</div>
              {simState
                ? <RegistersPanel registers={simState.registers} prev={prevRegs} />
                : <div className="rp-placeholder">Registers will appear after initialization.</div>}
            </div>
          )}

          {/* ── Memory tab ── */}
          {rightTab === 'memory' && (
            <div className="rp-body">
              <MemoryPanel
                memory={simState?.memory ?? null}
                pc={simState?.pc ?? 0}
                memAddrStr={memAddrStr}
                onAddrChange={setMemAddr}
              />
            </div>
          )}

          {/* ── Trace tab ── */}
          {rightTab === 'trace' && (
            <div className="rp-body">
              <TracePanel trace={trace} onClear={() => setTrace([])} />
            </div>
          )}

          {/* ── Output tab ── */}
          {rightTab === 'output' && (
            <div className="rp-body">
              <OutputPanel output={simState?.output ?? ''} />
            </div>
          )}
        </div>
      </div>

      {/* ─── Bottom bar ─── */}
      <div className="bottom-bar">
        <div className="bot-tabs">
          <button className={`bot-tab ${bottomTab === 'console' ? 'active' : ''}`} onClick={() => setBotTab('console')}>Console</button>
          <button className={`bot-tab ${bottomTab === 'binary' ? 'active' : ''}`}  onClick={() => setBotTab('binary')}>Machine Code</button>
        </div>
        <div className="bot-content">
          {bottomTab === 'console' && (
            <div className="console-lines" ref={consoleRef}>
              {consoleLines.map((l, i) => (
                <span key={i} className={`cl ${l.cls}`}>{l.t}</span>
              ))}
            </div>
          )}
          {bottomTab === 'binary' && (
            <BinaryPanel binary={binary} pc={simState?.pc ?? 0} isaName={isa} />
          )}
        </div>
      </div>
    </div>
  );
}
