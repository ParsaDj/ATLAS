import { StrictMode, useEffect, useRef, useState, type FormEvent } from "react";
import { createRoot } from "react-dom/client";
import {
  api,
  download,
  type Robot,
  type Mission,
  type Incident,
  type Event,
  type Investigation,
  type MaintenanceTicket,
  type User,
  type AuditLog,
  type TechnicalDocument,
  type LoginResult,
  type Position,
  type BuildInfo,
  rememberCsrf,
} from "./api";
import "./style.css";

type Selection = { kind: "robots" | "missions" | "incidents"; id: string };
const label = (text: string) => text.replaceAll("_", " ").replaceAll(".", " ");
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

function Root() {
  const [user, setUser] = useState<User | null | undefined>(undefined);
  useEffect(() => {
    api<User>("/api/auth/me")
      .then(setUser)
      .catch(() => setUser(null));
  }, []);
  if (user === undefined)
    return <div className="auth-loading">Loading ATLAS…</div>;
  if (!user) return <Login onLogin={setUser} />;
  return (
    <App
      user={user}
      onLogout={async () => {
        await api<void>("/api/auth/logout", { method: "POST" });
        rememberCsrf(null);
        setUser(null);
      }}
    />
  );
}

function Login({ onLogin }: { onLogin: (user: User) => void }) {
  const [username, setUsername] = useState("atlas-admin");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <main className="login-page">
      <form
        className="login-card"
        onSubmit={async (event) => {
          event.preventDefault();
          setBusy(true);
          setError("");
          try {
            const result = await api<LoginResult>("/api/auth/login", {
              method: "POST",
              body: JSON.stringify({ username, password }),
            });
            rememberCsrf(result.csrf_token);
            onLogin(result.user);
          } catch (reason) {
            setError((reason as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <div className="login-brand">
          <span className="brand-mark">A</span>ATLAS
        </div>
        <h1>Operations sign in</h1>
        <p>Use your Northstar facility account to continue.</p>
        <label>
          Username
          <input
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
        </label>
        <label>
          Password
          <input
            type="password"
            autoComplete="current-password"
            required
            minLength={12}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}
        <button className="primary" disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
        <small>Synthetic environment · authorized local users only</small>
      </form>
    </main>
  );
}

function App({
  user,
  onLogout,
}: {
  user: User;
  onLogout: () => Promise<void>;
}) {
  const [view, setView] = useState("Overview");
  const [revision, setRevision] = useState(0);
  const [page, setPage] = useState(0);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const fleet = useResource<Robot[]>("/api/robots", revision);
  const build = useResource<BuildInfo>("/version");
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
            ["Knowledge", "◇"],
            ...(user.role === "administrator" ? [["Administration", "⌁"]] : []),
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
            <span>{user.username.slice(0, 2).toUpperCase()}</span>
            <div>
              {user.username}
              <small>{label(user.role)}</small>
            </div>
          </div>
        </div>
      </aside>
      <main>
        <header className="topbar">
          <span>
            Workspace <b>/</b> {view}
          </span>
          <div className="topbar-actions">
            <span className="environment">SIMULATION</span>
            <button onClick={() => void onLogout()}>Sign out</button>
          </div>
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
                      : view === "Incidents"
                        ? "Incident center"
                        : view === "Knowledge"
                          ? "Technical knowledge"
                        : "Security & audit"}
              </h1>
              <p>
                {view === "Overview"
                  ? "Your fleet, missions, and exceptions. All in one place."
                  : view === "Fleet"
                    ? "Live operational state from your five simulated robots."
                    : view === "Missions"
                      ? "Plan inspections, approve execution, and review the record."
                      : view === "Incidents"
                        ? "Follow each failure back to its recorded evidence."
                        : view === "Knowledge"
                          ? "Review the approved guidance used in incident investigations."
                        : "Manage local users and review accountable operational actions."}
              </p>
            </div>
            {["operator", "administrator"].includes(user.role) &&
              !["Knowledge", "Administration"].includes(view) && (
              <button className="primary" onClick={() => setCreateOpen(true)}>
                ＋ Create mission
              </button>
            )}
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
                        <td>
                          {m.status === "completed"
                            ? m.waypoints.length
                            : (m.completed_waypoints ?? 0)}{" "}
                          / {m.waypoints.length} points
                        </td>
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
          {view === "Administration" && (
            <Administration
              revision={revision}
              onChange={() => setRevision((value) => value + 1)}
            />
          )}
          {view === "Knowledge" && (
            <KnowledgeLibrary
              role={user.role}
              revision={revision}
              onChange={() => setRevision((value) => value + 1)}
            />
          )}
          <footer>
            ATLAS {build.data ? `v${build.data.version} · ${build.data.build_sha.slice(0, 12)}` : ""} · Intelligent robot operations{" "}
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
          role={user.role}
        />
      )}
    </div>
  );
}

function KnowledgeLibrary({
  role,
  revision,
  onChange,
}: {
  role: User["role"];
  revision: number;
  onChange: () => void;
}) {
  const approved = useResource<TechnicalDocument[]>(
    "/api/documents?approved=true",
    revision,
  );
  const drafts = useResource<TechnicalDocument[]>(
    role === "administrator" ? "/api/documents?approved=false" : null,
    revision,
  );
  const [form, setForm] = useState({
    id: "",
    version: "1.0",
    fault: "sensor_failure",
    title: "",
    content: "",
    next_step: "",
  });
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const documents = [...(drafts.data ?? []), ...(approved.data ?? [])];

  async function createRevision(event: FormEvent) {
    event.preventDefault();
    setBusy("create");
    setError("");
    setMessage("");
    try {
      await api<TechnicalDocument>("/api/documents", {
        method: "POST",
        body: JSON.stringify(form),
      });
      setForm({
        id: "",
        version: "1.0",
        fault: "sensor_failure",
        title: "",
        content: "",
        next_step: "",
      });
      setMessage("Draft revision created. Review it before approval.");
      onChange();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy("");
    }
  }

  async function approveRevision(document: TechnicalDocument) {
    setBusy(`${document.id}:${document.version}`);
    setError("");
    setMessage("");
    try {
      await api(
        `/api/documents/${encodeURIComponent(document.id)}/versions/${encodeURIComponent(document.version)}/approve`,
        { method: "POST" },
      );
      setMessage(`${document.id} version ${document.version} approved.`);
      onChange();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy("");
    }
  }

  return (
    <div className="knowledge-layout">
      {role === "administrator" && (
        <section className="panel">
          <PanelHeader
            title="New document revision"
            subtitle="Draft first; approval is a separate audited action"
          />
          <form className="knowledge-form" onSubmit={createRevision}>
            <div className="form-row">
              <label>
                Document ID
                <input
                  required
                  pattern="[A-Z0-9-]+"
                  placeholder="DOC-SENSOR-002"
                  value={form.id}
                  onChange={(event) =>
                    setForm({ ...form, id: event.target.value.toUpperCase() })
                  }
                />
              </label>
              <label>
                Version
                <input
                  required
                  pattern="[0-9]+(\.[0-9]+){0,2}"
                  value={form.version}
                  onChange={(event) =>
                    setForm({ ...form, version: event.target.value })
                  }
                />
              </label>
            </div>
            <label>
              Fault classification
              <select
                value={form.fault}
                onChange={(event) =>
                  setForm({ ...form, fault: event.target.value })
                }
              >
                <option value="sensor_failure">Sensor failure</option>
                <option value="low_battery">Low battery</option>
                <option value="disconnection">Disconnection</option>
                <option value="navigation_failure">Navigation failure</option>
              </select>
            </label>
            <label>
              Title
              <input
                required
                minLength={3}
                value={form.title}
                onChange={(event) =>
                  setForm({ ...form, title: event.target.value })
                }
              />
            </label>
            <label>
              Technical content
              <textarea
                required
                minLength={20}
                rows={6}
                value={form.content}
                onChange={(event) =>
                  setForm({ ...form, content: event.target.value })
                }
              />
            </label>
            <label>
              Recommended next step
              <textarea
                required
                minLength={3}
                rows={3}
                value={form.next_step}
                onChange={(event) =>
                  setForm({ ...form, next_step: event.target.value })
                }
              />
            </label>
            <button className="primary" disabled={busy === "create"}>
              {busy === "create" ? "Creating…" : "Create draft revision"}
            </button>
          </form>
        </section>
      )}
      <section className="panel knowledge-list">
        <PanelHeader
          title="Technical document library"
          subtitle="Exact revisions available to the investigation service"
        />
        {error && <div className="error" role="alert">{error}</div>}
        {message && <div className="success" role="status">{message}</div>}
        {!approved.data || (role === "administrator" && !drafts.data) ? (
          <Empty text={approved.error ?? drafts.error ?? "Loading document revisions…"} />
        ) : documents.length === 0 ? (
          <Empty text="No technical documents are available." />
        ) : (
          <div className="document-stack">
            {documents.map((document) => (
              <article className="document-card" key={`${document.id}:${document.version}`}>
                <div className="document-heading">
                  <div>
                    <code>{document.id}@{document.version}</code>
                    <h3>{document.title}</h3>
                  </div>
                  <Badge status={document.approved ? "approved" : "draft"} />
                </div>
                <p>{document.content}</p>
                <dl>
                  <dt>Fault</dt><dd>{label(document.fault)}</dd>
                  <dt>Next step</dt><dd>{document.next_step}</dd>
                  <dt>SHA-256</dt><dd><code>{document.sha256}</code></dd>
                </dl>
                {!document.approved && role === "administrator" && (
                  <button
                    className="primary"
                    disabled={busy === `${document.id}:${document.version}`}
                    onClick={() => void approveRevision(document)}
                  >
                    {busy === `${document.id}:${document.version}`
                      ? "Approving…"
                      : "Approve revision"}
                  </button>
                )}
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function Administration({
  revision,
  onChange,
}: {
  revision: number;
  onChange: () => void;
}) {
  const users = useResource<User[]>("/api/users", revision);
  const logs = useResource<AuditLog[]>("/api/audit-logs?limit=100", revision);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<User["role"]>("operator");
  const [error, setError] = useState("");
  return (
    <div className="admin-grid">
      <section className="panel">
        <PanelHeader
          title="Facility users"
          subtitle="Local accounts and server-enforced roles"
        />
        <form
          className="admin-form"
          onSubmit={async (event) => {
            event.preventDefault();
            setError("");
            try {
              await api<User>("/api/users", {
                method: "POST",
                body: JSON.stringify({ username, password, role }),
              });
              setUsername("");
              setPassword("");
              onChange();
            } catch (reason) {
              setError((reason as Error).message);
            }
          }}
        >
          <label>
            Username
            <input
              required
              minLength={3}
              pattern="[a-z0-9._-]+"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
            />
          </label>
          <label>
            Temporary password
            <input
              required
              type="password"
              minLength={12}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          <label>
            Role
            <select
              value={role}
              onChange={(e) => setRole(e.target.value as User["role"])}
            >
              <option value="operator">Operator</option>
              <option value="technician">Technician</option>
              <option value="administrator">Administrator</option>
            </select>
          </label>
          {error && (
            <div className="error" role="alert">
              {error}
            </div>
          )}
          <button className="primary">Create user</button>
        </form>
        <div className="user-list">
          {users.data?.map((account) => (
            <div key={account.id}>
              <strong>{account.username}</strong>
              <Badge status={account.role} />
            </div>
          ))}
        </div>
      </section>
      <section className="panel audit-panel">
        <PanelHeader
          title="Audit history"
          subtitle="Latest 100 authenticated operational actions"
        />
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Actor</th>
                <th>Action</th>
                <th>Resource</th>
              </tr>
            </thead>
            <tbody>
              {logs.data?.map((record) => (
                <tr key={record.id}>
                  <td>{time(record.occurred_at)}</td>
                  <td>{record.actor_username}</td>
                  <td>{label(record.action)}</td>
                  <td>
                    <code>
                      {record.resource_type}:{short(record.resource_id)}
                    </code>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!logs.data?.length && (
          <Empty text={logs.error ?? "No audit records yet."} />
        )}
      </section>
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
  role,
}: {
  selection: Selection;
  revision: number;
  onClose: () => void;
  onChange: () => void;
  onSelect: (s: Selection) => void;
  role: User["role"];
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
  const [ticketSummary, setTicketSummary] = useState("");
  const [technician, setTechnician] = useState("");
  const [resolution, setResolution] = useState("");
  const [replacementWaypoints, setReplacementWaypoints] = useState<Position[]>([]);
  const [replacementSourceId, setReplacementSourceId] = useState("");
  const [investigation, setInvestigation] = useState<Investigation | null>(
    null,
  );
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
  const tickets = useResource<MaintenanceTicket[]>(
    incident
      ? `/api/tickets?incident_id=${encodeURIComponent(incident.id)}`
      : null,
    revision,
  );
  const sourceMission = useResource<Mission>(
    incident?.mission_id
      ? `/api/missions/${encodeURIComponent(incident.mission_id)}`
      : null,
    revision,
  );
  const replacements = useResource<Mission[]>(
    incident
      ? `/api/missions?source_incident_id=${encodeURIComponent(incident.id)}`
      : null,
    revision,
  );
  useEffect(() => {
    if (sourceMission.data && sourceMission.data.id !== replacementSourceId) {
      setReplacementWaypoints(sourceMission.data.waypoints.map((point) => ({ ...point })));
      setReplacementSourceId(sourceMission.data.id);
    }
  }, [sourceMission.data, replacementSourceId]);
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
  async function runInvestigation() {
    setBusy(true);
    setError("");
    try {
      setInvestigation(
        await api<Investigation>(
          `/api/incidents/${encodeURIComponent(selection.id)}/investigate`,
          { method: "POST" },
        ),
      );
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function createTicket() {
    setBusy(true);
    setError("");
    try {
      await api(`/api/incidents/${selection.id}/tickets`, {
        method: "POST",
        body: JSON.stringify({
          summary: ticketSummary,
          assigned_technician: technician,
        }),
      });
      setTicketSummary("");
      setTechnician("");
      setMessage("Maintenance ticket drafted for human approval.");
      onChange();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function ticketAction(ticket: MaintenanceTicket, name: string) {
    setBusy(true);
    setError("");
    try {
      await api(`/api/tickets/${ticket.id}/${name}`, {
        method: "POST",
        body:
          name === "resolve" ? JSON.stringify({ resolution }) : undefined,
      });
      setResolution("");
      setMessage(
        name === "approve"
          ? "Maintenance work approved."
          : name === "start"
            ? "Maintenance work started."
            : "Ticket and incident resolved.",
      );
      onChange();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function downloadReport(kind: "missions" | "incidents", id: string) {
    setBusy(true);
    setError("");
    try {
      await download(`/api/${kind}/${encodeURIComponent(id)}/report.html`);
      setMessage("Customer report downloaded.");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function proposeReplacement() {
    setBusy(true);
    setError("");
    try {
      await api(`/api/incidents/${selection.id}/replacement-missions`, {
        method: "POST",
        body: JSON.stringify({ waypoints: replacementWaypoints }),
      });
      setMessage("Replacement mission proposed for separate approval.");
      onChange();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function approveReplacement(id: string) {
    setBusy(true);
    setError("");
    try {
      await api(`/api/missions/${id}/approve`, { method: "POST" });
      setMessage("Replacement mission approved and ready for execution.");
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
            {mission?.source_incident_id && (
              <button
                className="wide-link"
                onClick={() =>
                  onSelect({ kind: "incidents", id: mission.source_incident_id! })
                }
              >
                Open source incident →
              </button>
            )}
            {mission && (
              <>
                <button
                  className="wide-link"
                  disabled={busy}
                  onClick={() => void downloadReport("missions", mission.id)}
                >
                  Download inspection report ↓
                </button>
                <h4>Waypoint progress</h4>
                <p role="status">
                  {mission.status === "completed"
                    ? mission.waypoints.length
                    : (mission.completed_waypoints ?? 0)}{" "}
                  of {mission.waypoints.length} waypoints reached
                </p>
                <progress
                  aria-label="Mission waypoint progress"
                  max={mission.waypoints.length}
                  value={
                    mission.status === "completed"
                      ? mission.waypoints.length
                      : (mission.completed_waypoints ?? 0)
                  }
                  style={{ width: "100%", margin: "12px 0" }}
                />
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
                {mission.status === "pending" && role !== "technician" && (
                  <button
                    className="primary"
                    disabled={busy || !!resource.error}
                    onClick={() => void action("approve")}
                  >
                    {busy ? "Working…" : "Approve mission"}
                  </button>
                )}
                {["pending", "running"].includes(mission.status) &&
                  role !== "technician" && (
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
                <button
                  className="wide-link"
                  disabled={busy}
                  onClick={() => void downloadReport("incidents", incident.id)}
                >
                  Download incident report ↓
                </button>
                <h4>Replacement mission</h4>
                {replacements.error && (
                  <div role="alert" className="error">
                    Replacement missions unavailable: {replacements.error}
                  </div>
                )}
                {replacements.data?.length ? (
                  replacements.data.map((replacement) => (
                    <section
                      className="ticket-card"
                      aria-label="Replacement mission"
                      key={replacement.id}
                    >
                      <div className="ticket-heading">
                        <strong>Replacement inspection</strong>
                        <Badge status={replacement.status} />
                      </div>
                      <p>
                        {replacement.waypoints.length} waypoints · proposed by{" "}
                        {replacement.proposed_by}
                      </p>
                      <button
                        onClick={() =>
                          onSelect({ kind: "missions", id: replacement.id })
                        }
                      >
                        Open replacement mission →
                      </button>
                      {replacement.status === "pending" && role !== "technician" && (
                        <button
                          className="primary"
                          disabled={busy}
                          onClick={() => void approveReplacement(replacement.id)}
                        >
                          Approve replacement mission
                        </button>
                      )}
                    </section>
                  ))
                ) : sourceMission.data?.status === "failed" && role !== "technician" ? (
                  <form
                    className="ticket-form"
                    onSubmit={(event) => {
                      event.preventDefault();
                      void proposeReplacement();
                    }}
                  >
                    <p>
                      Review or edit the failed mission route before proposing a replacement.
                    </p>
                    {replacementWaypoints.map((point, index) => (
                      <div className="waypoint" key={index}>
                        <span>{index + 1}</span>
                        {(["x", "y"] as const).map((axis) => (
                          <label key={axis}>
                            {axis.toUpperCase()}
                            <input
                              aria-label={`Replacement waypoint ${index + 1} ${axis.toUpperCase()}`}
                              type="number"
                              step="any"
                              required
                              value={point[axis]}
                              onChange={(event) =>
                                setReplacementWaypoints((current) =>
                                  current.map((item, itemIndex) =>
                                    itemIndex === index
                                      ? { ...item, [axis]: Number(event.target.value) }
                                      : item,
                                  ),
                                )
                              }
                            />
                          </label>
                        ))}
                      </div>
                    ))}
                    <button
                      disabled={busy || replacementWaypoints.length === 0}
                    >
                      Propose replacement mission
                    </button>
                  </form>
                ) : replacements.data ? (
                  <p className="notice">No replacement mission is available.</p>
                ) : (
                  <p>Loading replacement workflow…</p>
                )}
                <h4>Evidence-based investigation</h4>
                {!investigation ? (
                  <button
                    className="primary"
                    disabled={busy || !!resource.error}
                    onClick={() => void runInvestigation()}
                  >
                    {busy ? "Investigating…" : "Investigate incident"}
                  </button>
                ) : (
                  <section
                    className="investigation"
                    aria-label="Investigation result"
                  >
                    <Badge status={investigation.confidence} />
                    <p>{investigation.finding}</p>
                    {investigation.hypotheses?.length ? (
                      <>
                        <h4>Ranked hypotheses</h4>
                        <ol>
                          {investigation.hypotheses.map((hypothesis) => (
                            <li key={`${hypothesis.cause}:${hypothesis.confidence}`}>
                              <strong>{Math.round(hypothesis.confidence * 100)}%</strong>{" "}
                              {hypothesis.cause}
                              {hypothesis.evidence_ids.length ? (
                                <small> Evidence: {hypothesis.evidence_ids.join(", ")}</small>
                              ) : null}
                            </li>
                          ))}
                        </ol>
                      </>
                    ) : null}
                    {investigation.missing_evidence?.length ? (
                      <>
                        <h4>Missing evidence</h4>
                        <ul>
                          {investigation.missing_evidence.map((item) => (
                            <li key={item}>{item}</li>
                          ))}
                        </ul>
                      </>
                    ) : null}
                    <h4>Suggested next step</h4>
                    <p>{investigation.recommended_next_step}</p>
                    <h4>Limits</h4>
                    <ul>
                      {investigation.limitations.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                    <h4>Citations</h4>
                    <div className="citation-list">
                      {investigation.citations.map((citation) => (
                        <code key={`${citation.type}:${citation.id}`}>
                          {citation.type}:{citation.id}
                          {citation.version ? `@${citation.version}` : ""}
                          {citation.sha256 ? ` · ${citation.sha256.slice(0, 12)}` : ""}
                        </code>
                      ))}
                    </div>
                    <small>
                      {investigation.generated_by}
                      {investigation.model
                        ? ` · ${investigation.model.status} · ${investigation.model.model} · ${investigation.model.prompt_version}`
                        : ""}
                    </small>
                  </section>
                )}
                <h4>Maintenance workflow</h4>
                {tickets.error && (
                  <div role="alert" className="error">
                    Maintenance tickets unavailable: {tickets.error}
                  </div>
                )}
                {tickets.data?.length ? (
                  tickets.data.map((ticket) => (
                    <section
                      className="ticket-card"
                      aria-label="Maintenance ticket"
                      key={ticket.id}
                    >
                      <div className="ticket-heading">
                        <strong>{ticket.summary}</strong>
                        <Badge status={ticket.status} />
                      </div>
                      <p>
                        Assigned to <strong>{ticket.assigned_technician}</strong>
                        <br />
                        <small>
                          Drafted by {ticket.created_by} · {time(ticket.created_at)}
                        </small>
                      </p>
                      {ticket.approved_by && (
                        <p>
                          Approved by {ticket.approved_by} ·{" "}
                          {time(ticket.approved_at)}
                        </p>
                      )}
                      {ticket.resolution && (
                        <p className="notice">Resolution: {ticket.resolution}</p>
                      )}
                      {ticket.status === "draft" && role !== "technician" && (
                        <button
                          className="primary"
                          disabled={busy}
                          onClick={() => void ticketAction(ticket, "approve")}
                        >
                          Approve maintenance work
                        </button>
                      )}
                      {ticket.status === "approved" &&
                        ["technician", "administrator"].includes(role) && (
                          <button
                            className="primary"
                            disabled={busy}
                            onClick={() => void ticketAction(ticket, "start")}
                          >
                            Start maintenance work
                          </button>
                        )}
                      {ticket.status === "in_progress" &&
                        ["technician", "administrator"].includes(role) && (
                          <form
                            className="ticket-form"
                            onSubmit={(event) => {
                              event.preventDefault();
                              void ticketAction(ticket, "resolve");
                            }}
                          >
                            <label>
                              Resolution
                              <textarea
                                required
                                minLength={3}
                                maxLength={2000}
                                value={resolution}
                                onChange={(event) =>
                                  setResolution(event.target.value)
                                }
                                placeholder="Describe the completed maintenance and verification"
                              />
                            </label>
                            <button
                              className="primary"
                              disabled={busy || resolution.trim().length < 3}
                            >
                              Resolve ticket and incident
                            </button>
                          </form>
                        )}
                    </section>
                  ))
                ) : role !== "technician" && incident.status === "open" ? (
                  <form
                    className="ticket-form"
                    onSubmit={(event) => {
                      event.preventDefault();
                      void createTicket();
                    }}
                  >
                    <label>
                      Work summary
                      <textarea
                        required
                        minLength={3}
                        maxLength={500}
                        value={ticketSummary}
                        onChange={(event) => setTicketSummary(event.target.value)}
                        placeholder="What should the technician inspect or repair?"
                      />
                    </label>
                    <label>
                      Assigned technician username
                      <input
                        required
                        minLength={3}
                        maxLength={50}
                        pattern="[a-z0-9._-]+"
                        value={technician}
                        onChange={(event) => setTechnician(event.target.value)}
                        placeholder="field-tech"
                      />
                    </label>
                    <button
                      disabled={
                        busy ||
                        ticketSummary.trim().length < 3 ||
                        technician.trim().length < 3
                      }
                    >
                      Draft maintenance ticket
                    </button>
                  </form>
                ) : tickets.data ? (
                  <p className="notice">No maintenance ticket is available.</p>
                ) : (
                  <p>Loading maintenance workflow…</p>
                )}
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
                        : e.navigation_status === "failed"
                          ? "Navigation failure"
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
    <Root />
  </StrictMode>,
);
