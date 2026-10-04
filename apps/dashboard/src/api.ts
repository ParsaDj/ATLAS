export type Position = { x: number; y: number };
export type Robot = {
  id: string;
  name: string;
  status: string;
  battery: number | null;
  position: Position | null;
  last_contact: string | null;
  mission_id: string | null;
};
export type Mission = {
  id: string;
  robot_id: string;
  status: string;
  waypoints: Position[];
  completed_waypoints?: number;
  execution_step?: number;
  created_at: string;
  started_at: string | null;
  ended_at: string | null;
  cancellation_reason?: string;
  source_incident_id?: string;
  replacement_for_mission_id?: string;
  proposed_by?: string;
};
export type Incident = {
  id: string;
  robot_id: string;
  mission_id: string | null;
  type: string;
  status: string;
  detected_at: string;
  event_ids: string[];
  resolution?: string | null;
};
export type MaintenanceTicket = {
  id: string;
  incident_id: string;
  summary: string;
  status: "draft" | "approved" | "in_progress" | "resolved";
  assigned_technician: string;
  created_at: string;
  created_by: string;
  approved_at: string | null;
  approved_by: string | null;
  started_at: string | null;
  resolved_at: string | null;
  resolution: string | null;
};
export type Event = {
  event_id: string;
  robot_id: string;
  mission_id: string | null;
  occurred_at: string;
  received_at: string;
  battery: number;
  sensor_status: string;
  navigation_status?: string;
  position: Position;
  mission_status: string;
};
export type Investigation = {
  incident_id: string;
  finding: string;
  confidence: "supported" | "limited" | "insufficient";
  limitations: string[];
  recommended_next_step: string;
  citations: { type: "event" | "mission" | "document"; id: string }[];
  generated_by: string;
};
export type User = {
  id: string;
  username: string;
  role: "operator" | "technician" | "administrator";
  active: boolean;
};
export type AuditLog = {
  id: string;
  actor_id: string | null;
  actor_username: string;
  action: string;
  resource_type: string;
  resource_id: string;
  occurred_at: string;
  details: Record<string, unknown>;
};
export type LoginResult = { user: User; csrf_token: string };

export function rememberCsrf(token: string | null) {
  if (token) localStorage.setItem("atlas_csrf", token);
  else localStorage.removeItem("atlas_csrf");
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const csrf = localStorage.getItem("atlas_csrf");
  const response = await fetch(path, {
    ...init,
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(csrf && init.method && init.method !== "GET"
        ? { "X-CSRF-Token": csrf }
        : {}),
      ...init.headers,
    },
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      message = typeof body.detail === "string" ? body.detail : message;
    } catch {
      /* Keep HTTP status if no JSON body. */
    }
    throw new Error(message);
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

export async function download(path: string) {
  const response = await fetch(path, { credentials: "same-origin" });
  if (!response.ok) throw new Error(`Download failed (${response.status})`);
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const filename = disposition.match(/filename="([^"]+)"/)?.[1] ?? "atlas-report.html";
  const url = URL.createObjectURL(await response.blob());
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
