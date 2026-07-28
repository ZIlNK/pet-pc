export type InstanceSummary = {
  pet_id: string;
  package: string;
  primary: boolean;
  position: { x: number; y: number; screen?: number };
  state: string;
  size: number;
  screen_index: number;
};

export type PetPackage = {
  name: string;
  author: string;
  version: string;
  description: string;
  preview_available: boolean;
  action_count: number;
};

export type InstanceConfig = InstanceSummary & {
  actions: Record<string, ActionConfig>;
  rest_reminder: Record<string, unknown>;
  movement: Record<string, unknown>;
  behavior: Record<string, unknown>;
  motion_mode: Record<string, unknown>;
  click_detection: { enabled?: boolean; zones?: unknown[] };
  agent: Record<string, unknown>;
  mode: string;
};

export type ActionConfig = { enabled?: boolean; weight?: number; animation_files?: string[] } & Record<string, unknown>;
export type GlobalSettings = Record<string, Record<string, unknown>> & {
  api: Record<string, unknown> & { running?: boolean };
  llm: Record<string, unknown> & { api_key_configured?: boolean };
  mcp: Record<string, unknown> & { openclaw_hooks_token_configured?: boolean; openclaw_secret_token_configured?: boolean };
};
export type Memory = { id: string; text: string };

export class ApiError extends Error {
  constructor(message: string, readonly status: number) { super(message); }
}

export const apiBase = window.controlCenter?.apiBase || "http://127.0.0.1:8080/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${apiBase}${path}`, init);
  } catch {
    throw new ApiError("桌宠本地 API 未连接。请启动桌宠后重试。", 0);
  }
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new ApiError(payload.error || `请求失败（${response.status}）`, response.status);
  return payload as T;
}

export const api = {
  health: () => request<{ connected: boolean; api_running: boolean }>("/control-center/health"),
  instances: () => request<{ instances: InstanceSummary[] }>("/instances"),
  instance: (id: string) => request<InstanceConfig>(`/instances/${encodeURIComponent(id)}`),
  createInstance: (packageName: string) => request<InstanceConfig>("/instances", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ package: packageName }) }),
  updateInstance: (id: string, update: object) => request<InstanceConfig>(`/instances/${encodeURIComponent(id)}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(update) }),
  removeInstance: (id: string) => request<{ success: boolean }>(`/instances/${encodeURIComponent(id)}`, { method: "DELETE" }),
  pets: () => request<{ pets: PetPackage[] }>("/control-center/pets"),
  preview: (name: string) => `${apiBase}/control-center/pets/${encodeURIComponent(name)}/preview`,
  createPet: (form: FormData) => request<{ name: string }>("/control-center/pets", { method: "POST", body: form }),
  importPet: (form: FormData) => request<{ name: string; overwritten: boolean }>("/control-center/pets/import", { method: "POST", body: form }),
  globalSettings: () => request<GlobalSettings>("/control-center/global-settings"),
  updateGlobalSettings: (value: object) => request<GlobalSettings>("/control-center/global-settings", { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(value) }),
  memories: (id: string) => request<{ memories: Memory[] }>(`/control-center/pets/${encodeURIComponent(id)}/memories`),
  addMemory: (id: string, text: string) => request<Memory>(`/control-center/pets/${encodeURIComponent(id)}/memories`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }) }),
  deleteMemory: (id: string, memoryId: string) => request<{ success: boolean }>(`/control-center/pets/${encodeURIComponent(id)}/memories/${encodeURIComponent(memoryId)}`, { method: "DELETE" }),
  clearMemories: (id: string) => request<{ success: boolean }>(`/control-center/pets/${encodeURIComponent(id)}/memories`, { method: "DELETE" }),
};
