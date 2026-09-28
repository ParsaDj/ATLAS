import { StrictMode, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  api,
  type Robot,
  type Mission,
  type Incident,
  type Event,
} from "./api";
import "./style.css";

type Selection = { kind: "robots" | "missions" | "incidents"; id: string };
const label = (text: string) => text.replaceAll("_", " ");
const short = (id: string) => id.slice(0, 8).toUpperCase();
const time = (value: string | null | undefined) =>
  value
    ? new Date(value).toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      })
    : "Not reported";
function Badge({ status }: { status: string }) {
  return (
    <span className={`badge ${status}`}>
      <i />
      {label(status)}
    </span>
  );
}

function useResource<T>(path: string | null, revision = 0) {
  const [state, setState] = useState<{
    data?: T;
    error?: string;
    updated?: string;
    path: string | null;
  }>({ path });
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const controller = new AbortController();
    setState({ path });
    async function refresh() {
      if (!path) return;
      try {
        const data = await api<T>(path, { signal: controller.signal });
        if (active) setState({ data, updated: new Date().toISOString(), path });
      } catch (error) {
        if (active)
          setState((previous) => ({
            ...previous,
            error: error instanceof Error ? error.message : "Connection failed",
            path,
          }));
      } finally {
        if (active) timer = setTimeout(refresh, 5000);
      }
    }
    void refresh();
    return () => {
      active = false;
      controller.abort();
      clearTimeout(timer);
    };
  }, [path, revision]);
  return state.path === path ? state : { path };
}

function Pager({
  page,
  count,
  onChange,
}: {
  page: number;
  count: number;
  onChange: (page: number) => void;
}) {
  return (
    <div className="pager">
      <span>Page {page + 1} · up to 10 records</span>
      <div>
        <button disabled={page === 0} onClick={() => onChange(page - 1)}>
          ← Previous
        </button>
        <button disabled={count < 10} onClick={() => onChange(page + 1)}>
          Next →
        </button>
      </div>
    </div>
  );
}

function App() {
  const [view, setView] = useState("Overview");
  const [revision, setRevision] = useState(0);
  const [page, setPage] = useState(0);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const fleet = useResource<Robot[]>("/api/robots", revision);
  const missions = useResource<Mission[]>(
    `/api/missions?limit=10&offset=${view === "Missions" ? page * 10 : 0}`,
    revision,
  );
  const incidents = useResource<Incident[]>(
    `/api/incidents?limit=10&offset=${view === "Incidents" ? page * 10 : 0}`,
    revision,
  );
  const robots = fleet.data ?? [];
  const errors = [fleet.error, missions.error, incidents.error].filter(Boolean);
  const healthy = robots.filter((r) => r.status === "online").length;
  const attention = robots.filter((r) =>
    ["attention", "disconnected"].includes(r.status),
  ).length;
  function navigate(next: string) {
    setView(next);
    setPage(0);
  }
  return (
    <div className="shell">
      <aside className="sidebar">
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            navigate("Overview");
          }}
        >
          <span className="brand-mark">A</span>ATLAS
        </a>
        <div className="workspace">
          <span className="workspace-icon">N</span>
          <div>
            Northstar Industries<small>Inspection operations</small>
          </div>
          <span>⌄</span>
        </div>
        <div className="nav-label">WORKSPACE</div>
        <nav>
          {[
            ["Overview", "◫"],
            ["Fleet", "◈"],
            ["Missions", "⇢"],
            ["Incidents", "⚑"],
          ].map(([name, icon]) => (
            <button
              key={name}
              className={view === name ? "nav active" : "nav"}
              aria-current={view === name ? "page" : undefined}
              onClick={() => navigate(name)}
            >
              <span>{icon}</span>
              {name}
              {name === "Incidents" && (
                <span className="nav-number">
                  {incidents.data?.length ?? "—"}
                </span>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="sandbox">
            <span className="status-dot" />
            Synthetic environment<small>Fictional facility · no hardware</small>
          </div>
          <div className="profile">
            <span>OP</span>
            <div>
              Local operator<small>Development workspace</small>
            </div>
          </div>
        </div>
      </aside>
      <main>
        <header className="topbar">
          <span>
            Workspace <b>/</b> {view}
          </span>
          <span className="environment">SIMULATION</span>
        </header>
        <div className="content">
          <div className="page-heading">
            <div>
              <div className="eyebrow">NORTHSTAR / FACILITY 01</div>
              <h1>
                {view === "Overview"
                  ? "Operations overview"
                  : view === "Fleet"
                    ? "Robot fleet"
                    : view === "Missions"
                      ? "Inspection missions"
                      : "Incident center"}
              </h1>
              <p>
                {view === "Overview"
                  ? "Your fleet, missions, and exceptions. All in one place."
                  : view === "Fleet"
                    ? "Live operational state from your five simulated robots."
                    : view === "Missions"
                      ? "Plan inspections, approve execution, and review the record."
                      : "Follow each failure back to its recorded evidence."}
              </p>
            </div>
            <button className="primary" onClick={() => setCreateOpen(true)}>
              ＋ Create mission
            </button>
          </div>
          <div className="connection">
            <span>
              <i
                className={errors.length ? "status-dot danger" : "status-dot"}
              />
              {errors.length
                ? "Connection interrupted · displayed data may be stale"
                : fleet.updated
                  ? "API connected · refreshes every 5 seconds"
                  : "Connecting to API…"}
            </span>
            <span>Last fleet update {time(fleet.updated)}</span>
          </div>
          {errors.length > 0 && (
            <div role="alert" className="error">
              {[...new Set(errors)].join(" · ")}{" "}
              <button onClick={() => setRevision((v) => v + 1)}>
                Retry connection
              </button>
            </div>
          )}
          {view === "Overview" && (
            <>
              <section className="metrics">
                <Metric
                  title="Fleet size"
                  value={fleet.data ? String(robots.length) : "—"}
                  note="Registered robots"
                  icon="◈"
                />
                <Metric
                  title="Robots online"
                  value={fleet.data ? String(healthy) : "—"}
                  note="Reporting without faults"
                  icon="↗"
                />
                <Metric
                  title="Needs attention"
                  value={fleet.data ? String(attention) : "—"}
                  note="Fault or lost connection"
                  icon="!"
                  warning={attention > 0}
                />
                <Metric
                  title="Recent incidents"
                  value={incidents.data ? String(incidents.data.length) : "—"}
                  note="Latest 10 records"
                  icon="⚑"
                />
              </section>
              <section className="overview-grid">
                <div className="panel">
                  <PanelHeader
                    title="Fleet position"
                    subtitle="Last reported coordinates · synthetic facility"
                  />
                  <FleetMap robots={robots} />
                  <div className="map-legend">
                    <span>
                      <i className="status-dot" />
                      Online
                    </span>
                    <span>
                      <i className="status-dot danger" />
                      Needs attention
                    </span>
                    <span>Coordinates in simulation units</span>
                  </div>
                </div>
                <div className="panel">
                  <PanelHeader
                    title="Attention queue"
                    subtitle="Most recent incidents"
                  />
                  <div className="incident-stack">
                    {!incidents.data ? (
                      <Empty
                        text={
                          incidents.error
                            ? "Incidents unavailable."
                            : "Loading incidents…"
                        }
                      />
                    ) : incidents.data.length === 0 ? (
                      <Empty text="No incidents recorded. Run the simulator to begin." />
                    ) : (
                      incidents.data.slice(0, 4).map((i) => (
                        <button
                          className="incident-item"
                          key={i.id}
                          onClick={() =>
                            setSelection({ kind: "incidents", id: i.id })
                          }
                        >
                          <span className="incident-icon">!</span>
                          <span>
                            <strong>{label(i.type)}</strong>
                            <small>
                              {i.robot_id} · {time(i.detected_at)}
                            </small>
                          </span>
                          <span>↗</span>
                        </button>
                      ))
                    )}
                  </div>
                  <button
                    className="panel-link"
                    onClick={() => navigate("Incidents")}
                  >
                    View incident history <span>→</span>
                  </button>
                </div>
              </section>
            </>
          )}
          {(view === "Overview" || view === "Fleet") && (
            <section className="panel">
              <PanelHeader
                title="Fleet status"
                subtitle="Select a robot to inspect its latest telemetry"
              />
              <div className="robot-grid">
                {!fleet.data ? (
                  <Empty
                    text={fleet.error ? "Fleet unavailable." : "Loading fleet…"}
                  />
                ) : (
                  robots.map((robot) => (
                    <button
                      className="robot-card"
                      key={robot.id}
                      onClick={() =>
                        setSelection({ kind: "robots", id: robot.id })
                      }
                    >
                      <div className="robot-top">
                        <span className="robot-glyph">▣</span>
                        <span>↗</span>
                      </div>
                      <h3>{robot.name}</h3>
                      <span className="robot-id">{robot.id.toUpperCase()}</span>
                      <Badge status={robot.status} />
                      <div className="battery-row">
                        <span>Battery</span>
                        <strong>
                          {robot.battery === null ? "—" : `${robot.battery}%`}
                        </strong>
                      </div>
                      <div className="battery">
                        <div
                          style={{ width: `${robot.battery ?? 0}%` }}
                          className={
                            robot.battery !== null && robot.battery < 20
                              ? "low"
                              : ""
                          }
                        />
                      </div>
                      <small className="last-contact">
                        {time(robot.last_contact)}
                      </small>
                    </button>
                  ))
                )}
              </div>
            </section>
          )}
          {view === "Missions" && (
            <section className="panel">
              <PanelHeader
                title="Mission history"
                subtitle="Creating a mission saves a proposal; approval starts it."
              />
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Mission</th>
                      <th>Robot</th>
                      <th>Progress</th>
                      <th>Status</th>
                      <th>Created</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {missions.data?.map((m) => (
                      <tr key={m.id}>
                        <td className="mono">{short(m.id)}</td>
                        <td>{m.robot_id}</td>
                        <td>{m.status === "completed" ? m.waypoints.length : (m.completed_waypoints ?? 0)} / {m.waypoints.length} points</td>
                        <td>
                          <Badge status={m.status} />
                        </td>
                        <td>{time(m.created_at)}</td>
                        <td>
                          <button
                            onClick={() =>
                              setSelection({ kind: "missions", id: m.id })
                            }
                          >
                            Open →
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {!missions.data?.length && (
                  <Empty
                    text={
                      missions.data
                        ? "No missions on this page."
                        : missions.error
                          ? "Mission history unavailable."
                          : "Loading missions…"
                    }
                  />
                )}
              </div>
              <Pager
                page={page}
                count={missions.data?.length ?? 0}
                onChange={setPage}
              />
            </section>
          )}
          {view === "Incidents" && (
            <section className="panel">
              <PanelHeader
                title="Incident history"
                subtitle="Operational alerts from recorded telemetry and heartbeat monitoring"
              />
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Incident</th>
                      <th>Robot</th>
                      <th>Status</th>
                      <th>Detected</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {incidents.data?.map((i) => (
                      <tr key={i.id}>
                        <td>
                          <strong>{label(i.type)}</strong>
                          <small className="mono table-sub">
                            {short(i.id)}
                          </small>
                        </td>
                        <td>{i.robot_id}</td>
                        <td>
                          <Badge status={i.status} />
                        </td>
                        <td>{time(i.detected_at)}</td>
                        <td>
                          <button
                            onClick={() =>
                              setSelection({ kind: "incidents", id: i.id })
                            }
                          >
                            Investigate →
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {!incidents.data?.length && (
                  <Empty
                    text={
                      incidents.data
                        ? "No incidents on this page."
                        : incidents.error
                          ? "Incident history unavailable."
                          : "Loading incidents…"
                    }
                  />
                )}
              </div>
              <Pager
                page={page}
                count={incidents.data?.length ?? 0}
                onChange={setPage}
              />
            </section>
          )}
          <footer>
            ATLAS · Intelligent robot operations{" "}
            <span>Independent project / synthetic data only</span>
          </footer>
        </div>
      </main>
      {createOpen && (
        <CreateMission
          robots={robots}
          onClose={() => setCreateOpen(false)}
          onCreated={(m) => {
            setCreateOpen(false);
            setRevision((v) => v + 1);
            setSelection({ kind: "missions", id: m.id });
          }}
        />
      )}
      {selection && (
        <Details
          key={`${selection.kind}:${selection.id}`}
          selection={selection}
          revision={revision}
          onClose={() => setSelection(null)}
          onChange={() => setRevision((v) => v + 1)}
          onSelect={setSelection}
        />
      )}
    </div>
  );
}
function Metric({
  title,
  value,
  note,
  icon,
  warning = false,
}: {
  title: string;
  value: string;
  note: string;
  icon: string;
  warning?: boolean;
}) {
  return (
    <div className="metric">
      <div>
        {title}
        <span>{icon}</span>
      </div>
      <strong className={warning ? "warning" : ""}>{value}</strong>
      <small>{note}</small>
    </div>
  );
}
function PanelHeader({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div className="panel-heading">
      <h2>{title}</h2>
      <p>{subtitle}</p>
    </div>
  );
}
function Empty({ text }: { text: string }) {
  return <div className="empty">{text}</div>;
}
function FleetMap({ robots }: { robots: Robot[] }) {
  const located = robots.filter((r) => r.position);
  const xs = located.map((r) => r.position!.x),
    ys = located.map((r) => r.position!.y);
  const minX = Math.min(0, ...xs),
    maxX = Math.max(10, ...xs),
    minY = Math.min(0, ...ys),
    maxY = Math.max(7, ...ys);
  return (
    <div className="map">
      <div className="map-label">
        FACILITY 01 <span>POSITION VIEW</span>
      </div>
      <svg
        viewBox="0 0 620 255"
        role="img"
        aria-label="Last reported robot positions in synthetic facility"
      >
        <defs>
          <pattern
            id="grid"
            width="25"
            height="25"
            patternUnits="userSpaceOnUse"
          >
            <path
              d="M 25 0 L 0 0 0 25"
              fill="none"
              stroke="#d8e0dd"
              strokeWidth=".6"
            />
          </pattern>
        </defs>
        <rect width="620" height="255" fill="url(#grid)" />
        <rect
          x="35"
          y="40"
          width="550"
          height="180"
          rx="10"
          fill="none"
          stroke="#b7c9c0"
          strokeDasharray="5 5"
        />
        <text x="50" y="63" fill="#89978f" fontSize="10">
          SYNTHETIC COORDINATE SPACE
        </text>
        {located.map((r) => (
          <g
            key={r.id}
            transform={`translate(${70 + ((r.position!.x - minX) / (maxX - minX)) * 480},${195 - ((r.position!.y - minY) / (maxY - minY)) * 110})`}
          >
            <circle
              r="17"
              fill={r.status === "online" ? "#daf1e8" : "#fae6dc"}
            />
            <circle
              r="7"
              fill={r.status === "online" ? "#228666" : "#b65c35"}
            />
            <text x="22" y="4" fontSize="11" fill="#34423a">
              {r.name}
            </text>
          </g>
        ))}
        {!located.length && (
          <text
            x="310"
            y="135"
            textAnchor="middle"
            fill="#718178"
            fontSize="13"
          >
            Awaiting first robot positions
          </text>
        )}
      </svg>
    </div>
  );
}
function Modal({
  title,
  onClose,
  children,
  wide = false,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current!;
    dialog.showModal();
    return () => dialog.close();
  }, []);
  return (
    <dialog
      ref={ref}
      className={wide ? "drawer" : "modal"}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      aria-label={title}
    >
      <div className="dialog-heading">
        <h2>{title}</h2>
        <button onClick={onClose} aria-label="Close dialog">
          ✕
        </button>
      </div>
      {children}
    </dialog>
  );
}
function CreateMission({
  robots,
  onClose,
  onCreated,
}: {
  robots: Robot[];
  onClose: () => void;
  onCreated: (m: Mission) => void;
}) {
  const [robot, setRobot] = useState(robots[0]?.id ?? "");
  const [points, setPoints] = useState([
    { x: "3", y: "2" },
    { x: "7", y: "4" },
  ]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <Modal title="Create inspection mission" onClose={onClose}>
      <form
        className="form"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError("");
          try {
            const mission = await api<Mission>("/api/missions", {
              method: "POST",
              body: JSON.stringify({
                robot_id: robot,
                waypoints: points.map((p) => ({
                  x: Number(p.x),
                  y: Number(p.y),
                })),
              }),
            });
            onCreated(mission);
          } catch (err) {
            setError((err as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <p>
          Save a mission proposal, review its waypoints, then approve it
          separately.
        </p>
        <label>
          Assigned robot
          <select
            required
            value={robot}
            onChange={(e) => setRobot(e.target.value)}
          >
            <option value="" disabled>
              Select a robot
            </option>
            {robots.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name} · {r.status}
              </option>
            ))}
          </select>
        </label>
        <div className="field-title">
          Inspection waypoints <small>Simulation coordinates</small>
        </div>
        {points.map((p, i) => (
          <div className="waypoint" key={i}>
            <span>{String(i + 1).padStart(2, "0")}</span>
            <label>
              X coordinate {i + 1}
              <input
                type="number"
                step="any"
                required
                value={p.x}
                onChange={(e) =>
                  setPoints(
                    points.map((p, j) =>
                      j === i ? { ...p, x: e.target.value } : p,
                    ),
                  )
                }
              />
            </label>
            <label>
              Y coordinate {i + 1}
              <input
                type="number"
                step="any"
                required
                value={p.y}
                onChange={(e) =>
                  setPoints(
                    points.map((p, j) =>
                      j === i ? { ...p, y: e.target.value } : p,
                    ),
                  )
                }
              />
            </label>
            <button
              type="button"
              aria-label={`Remove waypoint ${i + 1}`}
              disabled={points.length === 1}
              onClick={() => setPoints(points.filter((_, j) => i !== j))}
            >
              −
            </button>
          </div>
        ))}
        <button
          type="button"
          disabled={points.length >= 100}
          onClick={() => setPoints([...points, { x: "0", y: "0" }])}
        >
          ＋ Add waypoint
        </button>
        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}
        <button className="primary" disabled={busy || !robot}>
          {busy ? "Saving…" : "Save mission proposal"}
        </button>
      </form>
    </Modal>
  );
}
function Details({
  selection,
  revision,
  onClose,
  onChange,
  onSelect,
}: {
  selection: Selection;
  revision: number;
  onClose: () => void;
  onChange: () => void;
  onSelect: (s: Selection) => void;
}) {
  const resource = useResource<Robot | Mission | Incident>(
    `/api/${selection.kind}/${encodeURIComponent(selection.id)}`,
    revision,
  );
  const data = resource.data;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [reason, setReason] = useState("");
  const [message, setMessage] = useState("");
  const mission =
    selection.kind === "missions" ? (data as Mission | undefined) : undefined;
  const incident =
    selection.kind === "incidents" ? (data as Incident | undefined) : undefined;
  const robot =
    selection.kind === "robots" ? (data as Robot | undefined) : undefined;
  const eventPath =
    selection.kind === "robots"
      ? `/api/robots/${encodeURIComponent(selection.id)}/telemetry?limit=20`
      : selection.kind === "missions"
        ? `/api/events?mission_id=${encodeURIComponent(selection.id)}&limit=20`
        : incident
          ? `/api/events?${incident.mission_id ? "mission_id=" + encodeURIComponent(incident.mission_id) : "robot_id=" + encodeURIComponent(incident.robot_id)}&limit=20`
          : null;
  const events = useResource<Event[]>(eventPath, revision);
  async function action(name: string) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await api(`/api/missions/${selection.id}/${name}`, {
        method: "POST",
        body: name === "cancel" ? JSON.stringify({ reason }) : undefined,
      });
      setMessage(
        name === "approve"
          ? "Mission approved. The running simulator worker will pick it up."
          : "Mission cancelled. History retained.",
      );
      onChange();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      title={
        selection.kind === "robots"
          ? "Robot details"
          : selection.kind === "missions"
            ? "Mission details"
            : "Incident evidence"
      }
      onClose={onClose}
      wide
    >
      <div className="detail-content">
        {resource.error && (
          <div className="error" role="alert">
            Could not refresh details: {resource.error}
          </div>
        )}
        {!data ? (
          <Empty
            text={resource.error ? "Details unavailable." : "Loading details…"}
          />
        ) : (
          <>
            <div className="detail-title">
              <h3>
                {robot?.name ??
                  (incident ? label(incident.type) : "Inspection mission")}
              </h3>
              <Badge status={data.status} />
            </div>
            <code className="resource-id">{data.id}</code>
            <dl>
              {robot ? (
                <>
                  <dt>Battery</dt>
                  <dd>
                    {robot.battery === null
                      ? "Not reported"
                      : `${robot.battery}%`}
                  </dd>
                  <dt>Last contact</dt>
                  <dd>{time(robot.last_contact)}</dd>
                  <dt>Position</dt>
                  <dd>
                    {robot.position
                      ? `${robot.position.x}, ${robot.position.y}`
                      : "Not reported"}
                  </dd>
                </>
              ) : (
                <>
                  <dt>Assigned robot</dt>
                  <dd>
                    <button
                      onClick={() =>
                        onSelect({
                          kind: "robots",
                          id: (data as Mission | Incident).robot_id,
                        })
                      }
                    >
                      {(data as Mission | Incident).robot_id} ↗
                    </button>
                  </dd>
                  <dt>{incident ? "Detected" : "Created"}</dt>
                  <dd>{time(incident?.detected_at ?? mission?.created_at)}</dd>
                </>
              )}
            </dl>
            {(robot?.mission_id || incident?.mission_id) && (
              <button
                className="wide-link"
                onClick={() =>
                  onSelect({
                    kind: "missions",
                    id: (robot?.mission_id ?? incident?.mission_id)!,
                  })
                }
              >
                Open linked mission →
              </button>
            )}
            {mission && (
              <>
                <h4>Waypoint progress</h4>
                <p role="status">{mission.status === "completed" ? mission.waypoints.length : (mission.completed_waypoints ?? 0)} of {mission.waypoints.length} waypoints reached</p>
                <progress aria-label="Mission waypoint progress" max={mission.waypoints.length} value={mission.status === "completed" ? mission.waypoints.length : (mission.completed_waypoints ?? 0)} style={{width: "100%", margin: "12px 0"}} />
                <div className="waypoint-list">
                  {mission.waypoints.map((p, i) => (
                    <span key={i}>
                      {i + 1} · ({p.x}, {p.y})
                    </span>
                  ))}
                </div>
                {mission.cancellation_reason && (
                  <p>Cancellation reason: {mission.cancellation_reason}</p>
                )}
                {mission.status === "pending" && (
                  <button
                    className="primary"
                    disabled={busy || !!resource.error}
                    onClick={() => void action("approve")}
                  >
                    {busy ? "Working…" : "Approve mission"}
                  </button>
                )}
                {["pending", "running"].includes(mission.status) && (
                  <form
                    className="cancel-form"
                    onSubmit={(e) => {
                      e.preventDefault();
                      void action("cancel");
                    }}
                  >
                    <label>
                      Cancellation reason
                      <input
                        required
                        maxLength={500}
                        value={reason}
                        onChange={(e) => setReason(e.target.value)}
                        placeholder="Why should this mission stop?"
                      />
                    </label>
                    <button
                      disabled={busy || !reason.trim() || !!resource.error}
                    >
                      Cancel mission
                    </button>
                  </form>
                )}
              </>
            )}
            {message && (
              <div role="status" className="success">
                {message}
              </div>
            )}
            {error && (
              <div role="alert" className="error">
                {error}
              </div>
            )}
            {incident && (
              <>
                <h4>Triggering evidence</h4>
                {incident.event_ids.length ? (
                  incident.event_ids.map((id) => <Evidence key={id} id={id} />)
                ) : (
                  <p className="notice">
                    This incident was detected by the heartbeat monitor. No
                    individual telemetry event triggered it. Detection time:{" "}
                    {time(incident.detected_at)}.
                  </p>
                )}
              </>
            )}
            <h4>
              Event history <small>Latest 20 records</small>
            </h4>
            {events.error && (
              <div role="alert" className="error">
                Event history unavailable: {events.error}
              </div>
            )}
            {!events.data ? (
              <Empty
                text={
                  events.error ? "Could not load events." : "Loading events…"
                }
              />
            ) : events.data.length === 0 ? (
              <Empty text="No telemetry recorded yet." />
            ) : (
              events.data.map((e) => (
                <div className="event" key={e.event_id}>
                  <div>
                    <strong>
                      {e.sensor_status === "failed"
                        ? "Sensor failure"
                        : e.battery < 20
                          ? "Low battery"
                          : "Telemetry received"}
                    </strong>
                    <span>{e.battery}% battery</span>
                  </div>
                  <small>
                    Occurred {time(e.occurred_at)} · received{" "}
                    {time(e.received_at)}
                  </small>
                  <code>{e.event_id}</code>
                  <small>
                    Position ({e.position.x}, {e.position.y}) ·{" "}
                    {e.mission_status}
                  </small>
                </div>
              ))
            )}
          </>
        )}
      </div>
    </Modal>
  );
}
function Evidence({ id }: { id: string }) {
  const evidence = useResource<Event>(`/api/events/${encodeURIComponent(id)}`);
  return (
    <div className="evidence">
      <code>{id}</code>
      {evidence.error ? (
        <p role="alert">Evidence unavailable: {evidence.error}</p>
      ) : evidence.data ? (
        <p>
          Battery {evidence.data.battery}% · sensor{" "}
          {evidence.data.sensor_status}
          <br />
          {time(evidence.data.occurred_at)}
        </p>
      ) : (
        <p>Loading evidence…</p>
      )}
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
