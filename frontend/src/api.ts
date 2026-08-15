export interface AssembleResult {
  binary: string;
  error: string | null;
  success: boolean;
}

export interface ISAInfo {
  name: string;
  description: string;
  [key: string]: any;
}

export interface ExampleProgram {
  name: string;
  code: string;
  isa: string;
  description: string;
}

export interface SimState {
  registers: Record<string, number>;
  flags: { Z: boolean; C: boolean; O: boolean; N: boolean };
  memory: number[];
  halted: boolean;
  output: string;
}

export interface SimUpdate {
  status: string;
  state: SimState | null;
  error?: string;
}

export async function assembleCode(code: string, isa: string): Promise<AssembleResult> {
  const res = await fetch('/api/assemble', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code, isa })
  });
  return res.json();
}

export async function getISAInfo(name: string): Promise<ISAInfo> {
  const res = await fetch(`/api/isa/${name}`);
  return res.json();
}

export async function getExamples(): Promise<ExampleProgram[]> {
  const res = await fetch('/api/examples');
  return res.json();
}

export class SimulatorSocket {
  private ws: WebSocket | null = null;
  private onStateUpdate: (update: SimUpdate) => void;
  private url: string;

  constructor(onStateUpdate: (update: SimUpdate) => void) {
    this.onStateUpdate = onStateUpdate;
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    this.url = `${protocol}//${window.location.host}/api/simulate`;
  }

  connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      this.ws = new WebSocket(this.url);
      
      this.ws.onopen = () => resolve();
      
      this.ws.onerror = (err) => {
        console.error('WebSocket Error:', err);
        reject(err);
      };

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data) as SimUpdate;
          this.onStateUpdate(data);
        } catch (err) {
          console.error('Failed to parse websocket message', err);
        }
      };

      this.ws.onclose = () => {
        console.log('WebSocket connection closed');
        this.ws = null;
      };
    });
  }

  disconnect() {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  private send(action: string, payload: any = {}) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ action, ...payload }));
    } else {
      console.error('WebSocket is not connected');
    }
  }

  init(config: { isa: string; memory_architecture?: string; binary: string }) {
    this.send('init', { config });
  }

  step() {
    this.send('step');
  }

  run() {
    this.send('run');
  }

  reset() {
    this.send('reset');
  }
}
