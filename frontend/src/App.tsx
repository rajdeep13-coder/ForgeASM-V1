import React, { useState, useEffect, useRef, useMemo } from 'react';
import './App.css';
import {
  assembleCode,
  SimulatorSocket,
  getExamples,
  ExampleProgram,
  SimState,
  SimUpdate
} from './api';

const ISAS = [
  { id: 'risc1', name: 'RISC-1 (Stack)' },
  { id: 'risc2', name: 'RISC-2 (Accumulator)' },
  { id: 'risc3', name: 'RISC-3 (Register)' },
  { id: 'cisc', name: 'CISC' }
];

const ARCHITECTURES = [
  { id: 'neumann', name: 'Von Neumann' },
  { id: 'harvard', name: 'Harvard' }
];

export default function App() {
  const [code, setCode] = useState('// Enter your assembly code here\n');
  const [isa, setIsa] = useState('risc1');
  const [architecture, setArchitecture] = useState('neumann');
  
  const [allExamples, setAllExamples] = useState<Record<string, {name: string, code: string}[]>>({});
  const [selectedExample, setSelectedExample] = useState('');
  
  const [isAssembling, setIsAssembling] = useState(false);
  const [assembleError, setAssembleError] = useState<string | null>(null);
  const [binary, setBinary] = useState<string | null>(null);
  
  const [simState, setSimState] = useState<SimState | null>(null);
  const [prevRegisters, setPrevRegisters] = useState<Record<string, number>>({});
  const [status, setStatus] = useState<string>('Idle');
  
  const [memoryOffsetStr, setMemoryOffsetStr] = useState('0000');
  
  const socketRef = useRef<SimulatorSocket | null>(null);

  const currentExamples = allExamples[isa] || [];

  useEffect(() => {
    getExamples().then(data => {
      setAllExamples(data as any);
    }).catch(err => console.error('Failed to load examples:', err));
    
    socketRef.current = new SimulatorSocket((update: SimUpdate) => {
      setStatus(update.status);
      if (update.error) {
        setAssembleError(update.error);
      }
      if (update.state) {
        setSimState(prevState => {
          if (prevState) {
            setPrevRegisters(prevState.registers);
          }
          return update.state;
        });
      }
    });

    socketRef.current.connect().catch(console.error);

    return () => {
      if (socketRef.current) {
        socketRef.current.disconnect();
      }
    };
  }, []);

  const handleExampleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const name = e.target.value;
    setSelectedExample(name);
    const ex = currentExamples.find((x: any) => x.name === name);
    if (ex) {
      setCode(ex.code);
    }
  };

  const handleAssemble = async () => {
    setIsAssembling(true);
    setAssembleError(null);
    setBinary(null);
    setSimState(null);
    setPrevRegisters({});
    setStatus('Assembling...');
    
    try {
      const res = await assembleCode(code, isa);
      if (res.success) {
        setBinary(res.binary);
        setStatus('Assembled');
        
        // Initialize simulator
        if (socketRef.current) {
          socketRef.current.init({
            isa,
            memory_architecture: architecture,
            binary: res.binary
          });
        }
      } else {
        setAssembleError(res.error || 'Unknown assembly error');
        setStatus('Assembly Error');
      }
    } catch (err: any) {
      setAssembleError(err.message || 'Network error');
      setStatus('Network Error');
    } finally {
      setIsAssembling(false);
    }
  };

  const handleStep = () => {
    if (socketRef.current) {
      socketRef.current.step();
    }
  };

  const handleRun = () => {
    if (socketRef.current) {
      socketRef.current.run();
    }
  };

  const handleReset = () => {
    if (socketRef.current) {
      socketRef.current.reset();
      setPrevRegisters({});
    }
  };

  // Derived variables for UI
  const lineCount = code.split('\n').length;
  const lineNumbers = Array.from({ length: Math.max(1, lineCount) }, (_, i) => i + 1).join('\n');
  
  const memoryOffset = parseInt(memoryOffsetStr, 16) || 0;
  
  const formatHex = (val: number, pad: number) => {
    return val.toString(16).padStart(pad, '0').toUpperCase();
  };

  return (
    <div className="app-container">
      {/* Header */}
      <header className="app-header panel">
        <div className="brand">
          <h1>ForgeASM <span>Hardware Simulator</span></h1>
        </div>
        
        <div className="header-controls">
          {currentExamples.length > 0 && (
            <div className="select-group">
              <label>Example</label>
              <select value={selectedExample} onChange={handleExampleChange}>
                <option value="">-- Custom --</option>
                {currentExamples.map((ex: any) => (
                  <option key={ex.name} value={ex.name}>{ex.name}</option>
                ))}
              </select>
            </div>
          )}
        
          <div className="select-group">
            <label>Architecture</label>
            <select value={architecture} onChange={e => setArchitecture(e.target.value)}>
              {ARCHITECTURES.map(a => (
                <option key={a.id} value={a.id}>{a.name}</option>
              ))}
            </select>
          </div>
          
          <div className="select-group">
            <label>ISA</label>
            <select value={isa} onChange={e => setIsa(e.target.value)}>
              {ISAS.map(i => (
                <option key={i.id} value={i.id}>{i.name}</option>
              ))}
            </select>
          </div>
        </div>
      </header>

      {/* Main Workspace */}
      <div className="main-workspace">
        {/* Left Column: Editor & Controls */}
        <div className="editor-container panel">
          <div className="panel-header">
            <span>Assembly Editor</span>
            <span style={{ color: 'var(--text-muted)' }}>{status}</span>
          </div>
          <div className="editor-wrapper">
            <div className="line-numbers">{lineNumbers}</div>
            <textarea
              className="code-editor"
              value={code}
              onChange={e => setCode(e.target.value)}
              spellCheck={false}
            />
          </div>
        </div>
        
        <div className="controls-bar panel">
          <button 
            className="btn btn-primary" 
            onClick={handleAssemble}
            disabled={isAssembling}
          >
            {isAssembling ? 'Assembling...' : 'Assemble & Load'}
          </button>
          
          <div className="spacer"></div>
          
          <button 
            className="btn btn-success" 
            onClick={handleRun}
            disabled={!binary || simState?.halted || status === 'Running'}
          >
            Run
          </button>
          <button 
            className="btn btn-outline" 
            onClick={handleStep}
            disabled={!binary || simState?.halted || status === 'Running'}
          >
            Step
          </button>
          <button 
            className="btn btn-danger" 
            onClick={handleReset}
            disabled={!binary}
          >
            Reset
          </button>
        </div>

        {/* Right Column: State & Memory */}
        <div className="sidebar panel">
          <div className="state-panel">
            <div className="panel-header">Processor State</div>
            
            {/* Flags */}
            <div className="flags-container">
              {['Z', 'C', 'O', 'N'].map(flag => {
                const isActive = simState?.flags?.[flag as keyof typeof simState.flags] || false;
                return (
                  <div className="flag" key={flag}>
                    <span className="flag-label">{flag}</span>
                    <div className={`flag-value ${isActive ? 'active' : ''}`}>
                      {isActive ? '1' : '0'}
                    </div>
                  </div>
                );
              })}
            </div>
            
            {/* Registers */}
            <div className="registers-grid">
              {simState ? Object.entries(simState.registers).map(([name, val]) => {
                const changed = prevRegisters[name] !== undefined && prevRegisters[name] !== val;
                return (
                  <div className="register-cell" key={name}>
                    <span className="reg-name">{name}</span>
                    <span className={`reg-value ${changed ? 'changed' : ''}`}>
                      0x{formatHex(val, 4)}
                    </span>
                  </div>
                );
              }) : (
                <div style={{ padding: '16px', color: 'var(--text-muted)', gridColumn: '1 / span 2', textAlign: 'center' }}>
                  Assemble code to view registers
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Bottom Area: Output & Memory */}
      <div className="output-area">
        <div className="panel">
          <div className="panel-header">Console Output</div>
          <div className="output-content">
            {assembleError && <div className="error-text">Error: {assembleError}</div>}
            {simState?.output && <div className="success-text">{simState.output}</div>}
            {status === 'Halted' && <div className="info-text">\n--- Execution Halted ---</div>}
            {!assembleError && !simState?.output && status === 'Idle' && (
              <div className="info-text">System Ready.</div>
            )}
          </div>
        </div>
        
        <div className="panel">
          <div className="panel-header">Memory Dump</div>
          <div className="memory-viewer">
            <div className="memory-controls">
              <span>Address: 0x</span>
              <input 
                type="text" 
                value={memoryOffsetStr}
                onChange={e => setMemoryOffsetStr(e.target.value.replace(/[^0-9a-fA-F]/g, '').slice(0, 4))}
                placeholder="0000"
              />
            </div>
            <div className="memory-grid">
              {simState?.memory ? (
                Array.from({ length: 8 }).map((_, rowIndex) => {
                  const baseAddr = memoryOffset + (rowIndex * 8);
                  if (baseAddr >= simState.memory.length) return null;
                  
                  const rowBytes = [];
                  let ascii = '';
                  
                  for (let i = 0; i < 8; i++) {
                    const addr = baseAddr + i;
                    if (addr < simState.memory.length) {
                      const val = simState.memory[addr];
                      rowBytes.push(formatHex(val, 2));
                      ascii += (val >= 32 && val <= 126) ? String.fromCharCode(val) : '.';
                    } else {
                      rowBytes.push('--');
                      ascii += '.';
                    }
                  }
                  
                  return (
                    <div className="memory-row" key={baseAddr}>
                      <span className="memory-address">{formatHex(baseAddr, 4)}</span>
                      <div className="memory-bytes">
                        {rowBytes.map((b, i) => (
                          <span className="memory-byte" key={i}>{b}</span>
                        ))}
                      </div>
                      <span className="memory-ascii">{ascii}</span>
                    </div>
                  );
                })
              ) : (
                <div style={{ color: 'var(--text-muted)', textAlign: 'center', marginTop: '32px' }}>
                  Memory not initialized
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
