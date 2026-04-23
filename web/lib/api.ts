const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

// ── Types ──────────────────────────────────────────────────────────────────────

export interface StageData {
  artifact: Record<string, unknown> | null;
  summary: string;
  feedback: string;
  approved: boolean;
}

export interface Session {
  session_id: string;
  project_name: string;
  current_stage: number;
  stage_data: Record<string, StageData>;
  created_at: string;
  updated_at: string;
}

export interface Stage5Result {
  success: boolean;
  dwxmz_path: string | null;
  image_path: string | null;
  topology_summary: string;
  connections_wired: number;
  connections_failed: number;
  connection_warning: boolean;
}

export interface HealthStatus {
  status: string;
  version?: string;
  dwsim?: boolean;
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function approvedStages(sess: Session): number[] {
  return Object.entries(sess.stage_data)
    .filter(([, v]) => v.approved)
    .map(([k]) => parseInt(k, 10))
    .sort();
}

export { approvedStages };

async function throwIfBad(res: Response): Promise<void> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch { /* ignore */ }
    throw new Error(detail);
  }
}

// ── API client ─────────────────────────────────────────────────────────────────

export const api = {
  // Sessions CRUD
  async createSession(project_name: string): Promise<Session> {
    const res = await fetch(`${API_URL}/sessions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_name }),
    });
    await throwIfBad(res);
    return res.json();
  },

  async listSessions(): Promise<Session[]> {
    const res = await fetch(`${API_URL}/sessions`, { cache: 'no-store' });
    await throwIfBad(res);
    return res.json();
  },

  async getSession(sessionId: string): Promise<Session> {
    const res = await fetch(`${API_URL}/sessions/${sessionId}`, { cache: 'no-store' });
    await throwIfBad(res);
    return res.json();
  },

  async deleteSession(sessionId: string): Promise<void> {
    const res = await fetch(`${API_URL}/sessions/${sessionId}`, { method: 'DELETE' });
    if (!res.ok && res.status !== 404) await throwIfBad(res);
  },

  // Stage runners — stages 1-4 return SSE token stream
  async *runStage(
    sessionId: string,
    stage: number,
    body: { user_input?: string; extra?: Record<string, unknown> } = {}
  ): AsyncGenerator<string, void, unknown> {
    const res = await fetch(`${API_URL}/sessions/${sessionId}/stages/${stage}/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    await throwIfBad(res);
    if (!res.body) return;

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const parts = buffer.split('\n\n');
      buffer = parts.pop() ?? '';

      for (const part of parts) {
        const line = part.trim();
        if (!line.startsWith('data:')) continue;
        const data = line.slice(5).trim();
        if (data === '[DONE]') return;
        try {
          const parsed = JSON.parse(data) as { token?: string };
          if (parsed.token) yield parsed.token;
        } catch { /* skip malformed */ }
      }
    }
  },

  // Stage 5 — synchronous JSON (calls DWSIM, may take ~30s)
  async runStage5(sessionId: string, feedback?: string): Promise<Stage5Result> {
    const res = await fetch(`${API_URL}/sessions/${sessionId}/stages/5/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ extra: feedback ? { feedback } : {} }),
    });
    await throwIfBad(res);
    return res.json();
  },

  // Gate operations
  async approveStage(sessionId: string, stage: number): Promise<{ session: Session; gate_message: string }> {
    const res = await fetch(`${API_URL}/sessions/${sessionId}/stages/${stage}/approve`, {
      method: 'POST',
    });
    await throwIfBad(res);
    return res.json();
  },

  async refineStage(sessionId: string, stage: number, feedback: string): Promise<Session> {
    const res = await fetch(`${API_URL}/sessions/${sessionId}/stages/${stage}/refine`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ feedback }),
    });
    await throwIfBad(res);
    const data = (await res.json()) as { session: Session };
    return data.session;
  },

  // Bundle download — triggers browser file save
  async downloadBundle(sessionId: string): Promise<void> {
    const res = await fetch(`${API_URL}/sessions/${sessionId}/download`);
    await throwIfBad(res);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    const cd = res.headers.get('Content-Disposition');
    a.download = cd?.match(/filename="([^"]+)"/)?.[1] ?? 'cpd-bundle.zip';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  },

  // Health
  async checkHealth(): Promise<HealthStatus> {
    try {
      const res = await fetch(`${API_URL}/health`, { cache: 'no-store' });
      return res.json();
    } catch {
      return { status: 'error' };
    }
  },
};
