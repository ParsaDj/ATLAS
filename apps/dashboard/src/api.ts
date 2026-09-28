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
};
export type Incident = {
  id: string;
  robot_id: string;
  mission_id: string | null;
  type: string;
  status: string;
  detected_at: string;
  event_ids: string[];
};
export type Event = {
  event_id: string;
  robot_id: string;
  mission_id: string | null;
  occurred_at: string;
  received_at: string;
  battery: number;
  sensor_status: string;
  position: Position;
  mission_status: string;
};
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init.headers },
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
  return response.json();
}
