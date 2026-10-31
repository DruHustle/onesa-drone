import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { createRoot } from "react-dom/client";
import { api, setCSRF, SessionChangedError } from "./api";
import FlightPlanPreview from "./FlightPlanPreview";
import type {
  Aircraft,
  Mission,
  Operations,
  User,
  History,
  Preferences,
  Sample,
  DispatchPreview,
} from "./types";
import "./onesa-foundation.css";
import "./style.css";
const DroneScene = lazy(() => import("./DroneScene"));
const groups = [
  ["OVERVIEW", "Dashboard"],
  ["FLEET", "Aircraft", "Fleet health", "Maintenance"],
  [
    "OPERATIONS",
    "Mission control",
    "Delivery management",
    "Route planning",
    "Flight plans",
    "Live telemetry",
  ],
  ["SIMULATION", "3D simulator", "Digital twins", "Scenarios"],
  ["INTELLIGENCE", "AI assistant", "Analytics"],
  ["SYSTEM", "Cybersecurity", "Infrastructure monitor", "Administration"],
];
const terminal = ["completed", "cancelled", "aborted"];
const human = (s: string) => s.replaceAll("_", " ");
function Icon({ name = "" }: { name?: string }) {
  const index = groups.flat().indexOf(name) % 4;
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      aria-hidden="true"
    >
      {index === 0 ? (
        <path d="M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z" />
      ) : index === 1 ? (
        <>
          <path d="m3 12 9-8 9 8-9 8zM12 4v16M3 12h18" />
        </>
      ) : index === 2 ? (
        <path d="M3 12h4l3-7 4 14 3-7h4" />
      ) : (
        <>
          <circle cx="6" cy="6" r="3" />
          <circle cx="18" cy="18" r="3" />
          <path d="M9 6h9v9M6 9v9h9" />
        </>
      )}
    </svg>
  );
}
function Badge({ state }: { state: string }) {
  return (
    <span
      className={`badge ${["aborted", "paused", "decommissioned", "degraded"].includes(state) ? "warn" : ["completed", "available", "healthy"].includes(state) ? "good" : ""}`}
    >
      <span aria-hidden="true">●</span> {human(state)}
    </span>
  );
}
function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}
function App() {
  const [user, setUser] = useState<User | null>(null),
    [boot, setBoot] = useState(true),
    [page, setPage] = useState("Dashboard"),
    [data, setData] = useState<Operations>({
      aircraft: [],
      missions: [],
      counts: {},
      mode: "simulation",
      at: 0,
      truncated: { aircraft: false, missions: false },
    }),
    [prefs, setPrefs] = useState<Preferences>({
      currency: "EUR",
      units: "metric",
      language: "en",
      region: "illustrative-campus",
    }),
    [selected, setSelected] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false),
    [connection, setConnection] = useState("connecting"),
    [mobile, setMobile] = useState(false),
    [modal, setModal] = useState<"aircraft" | "delivery" | null>(null),
    [edit, setEdit] = useState<Aircraft | null>(null),
    [track, setTrack] = useState("");
  const [lowPower, setLowPower] = useState(
      matchMedia("(max-width: 760px)").matches,
    ),
    [night, setNight] = useState(false),
    [weather, setWeather] = useState(false),
    [view, setView] = useState("orbit"),
    [history, setHistory] = useState<History | null>(null),
    [replay, setReplay] = useState<number | null>(null),
    [playing, setPlaying] = useState(false);
  const [inspectedAircraft, setInspectedAircraft] = useState<Aircraft | null>(
    null,
  );
  const [extraState, setExtra] = useState<any>(null),
    [answer, setAnswer] = useState("");
  const [dispatchState, setDispatch] = useState<{
      user_id: string;
      value: DispatchPreview;
    } | null>(null),
    [routeIndex, setRouteIndex] = useState(0);
  const dispatch =
    dispatchState?.user_id === user?.id ? dispatchState?.value : null;
  const extra = extraState?.page === page ? extraState.value : null;
  const flight =
    data.missions.find((m) => m.id === selected) ||
    data.missions.find((m) => !terminal.includes(m.state)) ||
    data.missions[0];
  const aircraft = data.aircraft.find((a) => a.id === flight?.aircraft_id);
  useEffect(() => setRouteIndex(0), [flight?.id]);
  const mounted = useRef(true);
  const currentAction = useRef(0);
  const resetWorkspace = useCallback(() => {
    currentAction.current++;
    setBusy(false);
    setNotice("");
    setData({
      aircraft: [],
      missions: [],
      counts: {},
      mode: "simulation",
      at: 0,
      truncated: { aircraft: false, missions: false },
    });
    setPrefs({
      currency: "EUR",
      units: "metric",
      language: "en",
      region: "illustrative-campus",
    });
    setHistory(null);
    setExtra(null);
    setSelected("");
    setAnswer("");
    setTrack("");
    setInspectedAircraft(null);
    setDispatch(null);
    setModal(null);
    setEdit(null);
    setReplay(null);
    setPlaying(false);
    setRouteIndex(0);
    setConnection("connecting");
  }, []);
  const run = useCallback(async (fn: () => Promise<unknown>) => {
    const action = ++currentAction.current;
    setBusy(true);
    setNotice("");
    try {
      await fn();
    } catch (e) {
      if (
        action === currentAction.current &&
        !(e instanceof SessionChangedError)
      )
        setNotice(e instanceof Error ? e.message : "Operation failed");
    } finally {
      if (action === currentAction.current) setBusy(false);
    }
  }, []);
  const refresh = useCallback(async () => {
    const d = await api<Operations>("/operations");
    setData(d);
  }, []);
  useEffect(() => {
    mounted.current = true;
    api<User>("/auth/me")
      .then((u) => {
        setUser(u);
        setCSRF(u.csrf);
      })
      .catch(() => {})
      .finally(() => setBoot(false));
    return () => {
      mounted.current = false;
    };
  }, []);
  useEffect(() => {
    if (!user) return;
    let stopped = false,
      source: EventSource | undefined,
      timer: ReturnType<typeof setTimeout>;
    void api<Operations>("/operations")
      .then((value) => {
        if (!stopped) setData(value);
      })
      .catch((e) => {
        if (!stopped) setNotice(e.message);
      });
    void api<Preferences>("/settings")
      .then((value) => {
        if (!stopped) setPrefs(value);
      })
      .catch((e) => {
        if (!stopped) setNotice(e.message);
      });
    let attempts = 0;
    function connect() {
      source = new EventSource("/api/v1/stream");
      source.addEventListener("telemetry", (event) => {
        if (stopped) return;
        attempts = 0;
        setConnection("receiving");
        setData(JSON.parse((event as MessageEvent).data));
      });
      source.addEventListener("expired", () => {
        if (stopped) return;
        source?.close();
        setCSRF("");
        resetWorkspace();
        setConnection("session expired");
        setUser(null);
      });
      source.addEventListener("unavailable", () => {
        if (!stopped) setConnection("storage unavailable");
      });
      source.onerror = () => {
        source?.close();
        if (stopped) return;
        setConnection("reconnecting");
        timer = setTimeout(
          connect,
          Math.min(30000, 1000 * 2 ** Math.min(attempts++, 5)),
        );
      };
    }
    connect();
    return () => {
      stopped = true;
      source?.close();
      clearTimeout(timer);
    };
  }, [user, refresh, resetWorkspace]);
  useEffect(() => {
    setExtra(null);
    setHistory(null);
    setReplay(null);
    setPlaying(false);
    if (!user) return;
    const path =
      page === "Cybersecurity"
        ? "/security"
        : page === "Infrastructure monitor"
          ? "/infrastructure"
          : page === "Scenarios"
            ? "/scenarios"
            : page === "Administration" && user.role === "admin"
              ? "/users"
              : null;
    if (path) {
      let cancelled = false;
      void api(path)
        .then((value) => {
          if (!cancelled) setExtra({ page, value });
        })
        .catch((e) => {
          if (!cancelled) setNotice(e.message);
        });
      return () => {
        cancelled = true;
      };
    }
  }, [page, user]);
  useEffect(() => {
    if (
      !flight ||
      ![
        "Mission control",
        "Live telemetry",
        "3D simulator",
        "Route planning",
      ].includes(page)
    )
      return;
    let cancelled = false;
    void api<History>(`/missions/${flight.id}/history`)
      .then((h) => {
        if (!cancelled) setHistory(h);
      })
      .catch((e) => setNotice(e.message));
    return () => {
      cancelled = true;
    };
  }, [flight?.id, flight?.state, page]);
  useEffect(() => {
    if (!playing || !history) return;
    const timer = setInterval(
      () =>
        setReplay((value) => {
          const next = (value || 0) + 1;
          if (next >= history.telemetry.length - 1) {
            setPlaying(false);
            return history.telemetry.length - 1;
          }
          return next;
        }),
      180,
    );
    return () => clearInterval(timer);
  }, [playing, history]);
  const navigate = (p: string) => {
    setPage(p);
    setMobile(false);
    setNotice("");
  };
  async function act(m: Mission, action: string, assignment?: string) {
    await run(async () => {
      await api(
        `/missions/${m.id}/commands`,
        "POST",
        {
          action,
          revision: m.revision,
          ...(action === "plan"
            ? { route_index: assignment ? 0 : routeIndex }
            : {}),
          ...(assignment ? { aircraft_id: assignment } : {}),
        },
        crypto.randomUUID(),
      );
      await refresh();
    });
  }
  async function aircraftAct(a: Aircraft, action: string, note = "") {
    await run(async () => {
      await api(
        `/aircraft/${a.id}/commands`,
        "POST",
        { action, revision: a.revision, note },
        crypto.randomUUID(),
      );
      await refresh();
    });
  }
  const distance = (n: number) =>
    prefs.units === "imperial"
      ? `${(n * 3.28084).toFixed(0)} ft`
      : `${n.toFixed(0)} m`;
  const canOperate = !!user && user.role !== "viewer";
  if (location.pathname.startsWith("/track/"))
    return <Tracking token={location.pathname.split("/")[2]} />;
  if (boot)
    return (
      <div className="initial">
        ONESA <span>Opening mission operations…</span>
      </div>
    );
  if (!user)
    return (
      <div className="login">
        <div className="login-visual">
          <span className="wordmark">
            ONESA <small>DRONE</small>
          </span>
          <p className="eyebrow">PHYSICAL AI / AUTONOMOUS LOGISTICS</p>
          <h1>
            Intelligent delivery.
            <br />
            Beyond roads.
          </h1>
          <p>
            Mission simulation, fleet intelligence and delivery orchestration in
            one operational workspace.
          </p>
          <div className="login-orbit" aria-hidden="true">
            ✧
          </div>
          <small>UNDER DEVELOPMENT · SIMULATION ONLY</small>
        </div>
        <main className="login-form">
          <p className="eyebrow">MISSION OPERATIONS</p>
          <h2>Sign in to your workspace</h2>
          <p>Use your individually provisioned operator account.</p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const f = new FormData(e.currentTarget);
              void run(async () => {
                const u = await api<User>("/auth/login", "POST", {
                  email: f.get("email"),
                  password: f.get("password"),
                });
                resetWorkspace();
                setCSRF(u.csrf);
                setUser(u);
              });
            }}
          >
            <label>
              Email
              <input
                name="email"
                type="email"
                required
                autoComplete="username"
              />
            </label>
            <label>
              Password
              <input
                name="password"
                type="password"
                required
                autoComplete="current-password"
                maxLength={200}
              />
            </label>
            <button className="primary" disabled={busy}>
              Sign in <span aria-hidden="true">→</span>
            </button>
          </form>
          {notice && (
            <p role="alert" className="error">
              {notice}
            </p>
          )}
          <p className="fine">
            Aircraft performance and environments are illustrative. This
            software does not authorize physical flight.
          </p>
        </main>
      </div>
    );
  const active = data.missions.filter((m) =>
    ["taking_off", "outbound", "delivering", "returning", "landing"].includes(
      m.state,
    ),
  );
  const scene = (
    <div className="visual">
      <Suspense
        fallback={
          <div className="scene-loading">Loading lightweight 3D campus…</div>
        }
      >
        <DroneScene
          mission={page === "Digital twins" ? undefined : flight}
          sample={replay !== null ? history?.telemetry[replay] : undefined}
          lowPower={lowPower}
          night={night}
          weather={weather}
          view={view}
          category={
            page === "Digital twins"
              ? inspectedAircraft?.category
              : aircraft?.category
          }
        />
      </Suspense>
      <div className="visual-top">
        <Badge
          state={replay !== null ? "replay" : flight?.state || "standby"}
        />
        <span>VIRTUAL AIRSPACE / {prefs.region.toUpperCase()}</span>
      </div>
      <div className="scene-controls">
        <label>
          Camera
          <select
            aria-label="Camera"
            value={view}
            onChange={(e) => setView(e.target.value)}
          >
            <option value="orbit">Orbit</option>
            <option value="inspect">Aircraft inspection</option>
            <option value="follow">Follow aircraft</option>
            <option value="first-person">First person</option>
          </select>
        </label>
        <label>
          <input
            type="checkbox"
            checked={night}
            onChange={(e) => setNight(e.target.checked)}
          />{" "}
          Night environment
        </label>
        <label>
          <input
            type="checkbox"
            checked={weather}
            onChange={(e) => setWeather(e.target.checked)}
          />{" "}
          Weather visual
        </label>
        <label>
          <input
            type="checkbox"
            checked={lowPower}
            onChange={(e) => setLowPower(e.target.checked)}
          />{" "}
          Low power
        </label>
      </div>
    </div>
  );
  const missionSelector = (
    <label className="mission-select">
      Selected mission
      <select
        value={flight?.id || ""}
        onChange={(e) => {
          setSelected(e.target.value);
          setReplay(null);
        }}
      >
        {!data.missions.length && <option value="">No missions</option>}
        {data.missions.map((m) => (
          <option key={m.id} value={m.id}>
            {m.label} · {human(m.state)}
          </option>
        ))}
      </select>
    </label>
  );
  const telemetry =
    flight &&
    (replay !== null ? history?.telemetry[replay] : flight.last_telemetry);
  return (
    <div className="app">
      <a className="skip-link" href="#main">
        Skip to operations
      </a>
      <aside className={mobile ? "sidebar open" : "sidebar"}>
        <a
          href="#dashboard"
          className="wordmark"
          onClick={() => navigate("Dashboard")}
        >
          ONESA <small>DRONE</small>
        </a>
        <div className="workspace">
          <span className="workspace-symbol">O</span>
          <div>
            Simulation workspace<small>{user.role} access</small>
          </div>
          <span aria-hidden="true">⌄</span>
        </div>
        <nav aria-label="Main navigation">
          {groups.map(([group, ...items]) => (
            <details key={group} open>
              <summary>{group}</summary>
              {items.map((item) => (
                <button
                  className={page === item ? "nav-item current" : "nav-item"}
                  key={item}
                  onClick={() => navigate(item)}
                  aria-current={page === item ? "page" : undefined}
                >
                  <Icon name={item} />
                  {item}
                </button>
              ))}
            </details>
          ))}
        </nav>
        <div className="sidebar-foot">
          <span className="simulation-dot" /> Simulation mode
          <small>Physical flight disabled</small>
          <button
            className="quiet"
            onClick={() =>
              void run(async () => {
                await api("/auth/logout", "POST", {});
                setCSRF("");
                resetWorkspace();
                setUser(null);
              })
            }
          >
            Sign out
          </button>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <button
            className="menu"
            aria-label="Toggle navigation"
            aria-expanded={mobile}
            onClick={() => setMobile(!mobile)}
          >
            ☰
          </button>
          <span>
            WORKSPACE <span className="separator">/</span> {page}
          </span>
          <div>
            <span className="connection">
              <span
                className={
                  connection === "receiving" ? "live-dot" : "pending-dot"
                }
              />
              {connection}
            </span>
            <span className="avatar" title={user.email}>
              {user.email[0].toUpperCase()}
            </span>
          </div>
        </header>
        <main id="main">
          <div className="page-heading">
            <div>
              <p className="eyebrow">ONESA DRONE / SIMULATION OPERATIONS</p>
              <h1>{page === "Dashboard" ? "Mission overview" : page}</h1>
              <p>
                {page === "Dashboard"
                  ? "A clear view of your aerial logistics operations."
                  : subtitles[page]}
              </p>
            </div>
            {canOperate && (
              <div className="actions">
                <button
                  onClick={() => {
                    setEdit(null);
                    setModal("aircraft");
                  }}
                >
                  + Register aircraft
                </button>
                <button
                  className="primary"
                  onClick={() => setModal("delivery")}
                >
                  + New delivery
                </button>
              </div>
            )}
          </div>
          <div className="simulation-banner">
            <span>SIMULATION ONLY</span>
            <p>
              Under development. All aircraft, telemetry and deliveries are
              virtual. No physical-flight controls.
            </p>
          </div>
          {notice && (
            <div className="error" role="alert">
              {notice}
              <button className="quiet" onClick={() => setNotice("")}>
                Dismiss
              </button>
            </div>
          )}
          {page === "Dashboard" && (
            <>
              <div className="metrics">
                <Metric
                  label="Aircraft in fleet"
                  value={data.aircraft.length}
                  foot={`${data.aircraft.filter((a) => a.status === "available" && !a.active_mission_id).length} available for simulation`}
                />
                <Metric
                  label="Active missions"
                  value={active.length}
                  foot="Virtual flights in progress"
                />
                <Metric
                  label="Completed deliveries"
                  value={data.missions.filter((m) => m.delivered).length}
                  foot="Within the latest 100 missions"
                />
                <Metric
                  label="Fleet battery"
                  value={
                    data.aircraft.length
                      ? `${Math.round(data.aircraft.reduce((s, a) => s + a.battery, 0) / data.aircraft.length)}%`
                      : "—"
                  }
                  foot="Illustrative energy model"
                />
              </div>
              <div className="section-heading">
                <h2>Live operations</h2>
                <button
                  className="quiet"
                  onClick={() => navigate("3D simulator")}
                >
                  Open simulator ↗
                </button>
              </div>
              {scene}
              <div className="two-col">
                <section>
                  <div className="section-heading">
                    <h2>Mission activity</h2>
                    <button
                      className="quiet"
                      onClick={() => navigate("Mission control")}
                    >
                      View all →
                    </button>
                  </div>
                  <MissionList
                    missions={data.missions.slice(0, 4)}
                    selected={flight?.id}
                    select={(m) => {
                      setSelected(m.id);
                      navigate("Mission control");
                    }}
                  />
                </section>
                <section>
                  <div className="section-heading">
                    <h2>Fleet readiness</h2>
                    <button
                      className="quiet"
                      onClick={() => navigate("Fleet health")}
                    >
                      Inspect fleet →
                    </button>
                  </div>
                  {!data.aircraft.length ? (
                    <Empty>Register an illustrative aircraft to begin.</Empty>
                  ) : (
                    data.aircraft.slice(0, 4).map((a) => (
                      <div className="fleet-row" key={a.id}>
                        <Icon name="Aircraft" />
                        <div>
                          <strong>{a.name}</strong>
                          <small>{human(a.category)}</small>
                        </div>
                        <div className="battery">
                          <span>{a.battery.toFixed(0)}%</span>
                          <meter
                            min="0"
                            max="100"
                            value={a.battery}
                            aria-label={`${a.name} battery`}
                          />
                        </div>
                        <Badge
                          state={a.active_mission_id ? "reserved" : a.status}
                        />
                      </div>
                    ))
                  )}
                </section>
              </div>
            </>
          )}
          {[
            "Aircraft",
            "Fleet health",
            "Maintenance",
            "Digital twins",
          ].includes(page) && (
            <>
              {page === "Digital twins" && scene}
              <div className="section-heading">
                <h2>Illustrative aircraft registry</h2>
                <p>{data.aircraft.length} aircraft</p>
              </div>
              {!data.aircraft.length ? (
                <Empty>
                  No aircraft registered. Add an illustrative configuration to
                  start.
                </Empty>
              ) : (
                <div className="aircraft-grid">
                  {data.aircraft.map((a) => (
                    <article key={a.id} className="aircraft-item">
                      <div className="aircraft-preview" aria-hidden="true">
                        <svg viewBox="0 0 260 150">
                          <g fill="none" stroke="currentColor" strokeWidth="5">
                            <path d="m85 50 90 55m-90 0 90-55" />
                            {[85, 175].flatMap((x) =>
                              [50, 105].map((y) => (
                                <ellipse
                                  key={`${x}-${y}`}
                                  cx={x}
                                  cy={y}
                                  rx="37"
                                  ry="12"
                                  strokeWidth="2"
                                />
                              )),
                            )}
                          </g>
                          <ellipse
                            cx="130"
                            cy="78"
                            rx="23"
                            ry="30"
                            fill="currentColor"
                          />
                          <path
                            d="M116 74h28"
                            stroke="var(--onesa-surface)"
                            strokeWidth="5"
                          />
                        </svg>
                        <span>{human(a.category)}</span>
                      </div>
                      <div className="aircraft-title">
                        <h3>{a.name}</h3>
                        <Badge
                          state={a.active_mission_id ? "reserved" : a.status}
                        />
                      </div>
                      <p>
                        {a.model}
                        <small>{a.manufacturer} · illustrative</small>
                      </p>
                      <dl className="specs">
                        <div>
                          <dt>Battery</dt>
                          <dd>{a.battery.toFixed(1)}%</dd>
                        </div>
                        <div>
                          <dt>Payload</dt>
                          <dd>
                            {prefs.units === "imperial"
                              ? (a.capacity * 2.20462).toFixed(1) + " lb"
                              : a.capacity + " kg"}
                          </dd>
                        </div>
                        <div>
                          <dt>Endurance</dt>
                          <dd>{a.endurance} min</dd>
                        </div>
                        <div>
                          <dt>Firmware</dt>
                          <dd>{a.firmware}</dd>
                        </div>
                      </dl>
                      {page === "Maintenance" && (
                        <ul className="maintenance-list">
                          {a.maintenance.length ? (
                            a.maintenance.slice(-4).map((m, i) => (
                              <li key={i}>
                                {new Date(m.at * 1000).toLocaleDateString()} ·{" "}
                                {m.action}: {m.note || "Recorded inspection"}
                              </li>
                            ))
                          ) : (
                            <li>No inspections recorded.</li>
                          )}
                        </ul>
                      )}
                      {canOperate && (
                        <div className="row-actions">
                          <button
                            onClick={() => {
                              setInspectedAircraft(a);
                              setView("inspect");
                              navigate("Digital twins");
                            }}
                          >
                            View 3D
                          </button>
                          <button
                            disabled={busy || !!a.active_mission_id}
                            onClick={() => {
                              setEdit(a);
                              setModal("aircraft");
                            }}
                          >
                            Edit
                          </button>
                          <button
                            disabled={busy || !!a.active_mission_id}
                            onClick={() =>
                              void aircraftAct(
                                a,
                                "inspect",
                                "Illustrative software inspection recorded by operator",
                              )
                            }
                          >
                            Inspect
                          </button>
                          <button
                            disabled={
                              busy ||
                              !!a.active_mission_id ||
                              a.status === "decommissioned"
                            }
                            onClick={() => void aircraftAct(a, "charge")}
                          >
                            Recharge
                          </button>
                          <button
                            disabled={busy || !!a.active_mission_id}
                            onClick={() =>
                              void aircraftAct(
                                a,
                                a.status === "decommissioned"
                                  ? "restore"
                                  : "decommission",
                              )
                            }
                          >
                            {a.status === "decommissioned"
                              ? "Restore"
                              : "Decommission"}
                          </button>
                        </div>
                      )}
                    </article>
                  ))}
                </div>
              )}
            </>
          )}
          {[
            "Mission control",
            "Delivery management",
            "Route planning",
            "Live telemetry",
            "3D simulator",
          ].includes(page) && (
            <>
              {missionSelector}
              {["3D simulator", "Route planning", "Mission control"].includes(
                page,
              ) && scene}
              {["Route planning", "Delivery management"].includes(page) && (
                <section
                  className="dispatch-preview"
                  aria-label="Dispatch planning"
                >
                  <div className="section-heading">
                    <h2>Suggested dispatch order</h2>
                    <button
                      disabled={busy}
                      onClick={() =>
                        void run(async () => {
                          setDispatch({
                            user_id: user.id,
                            value:
                              await api<DispatchPreview>("/dispatch/preview"),
                          });
                        })
                      }
                    >
                      Build dispatch preview
                    </button>
                  </div>
                  <p className="fine">
                    Sequence independent round trips with estimated battery,
                    scheduled start times and a 60-second turnaround. No
                    automatic recharge or transfer between depots.
                  </p>
                  {dispatch && (
                    <>
                      <p className="fine">
                        {dispatch.notice} Generated{" "}
                        {new Date(dispatch.at * 1000).toLocaleTimeString()}.
                      </p>
                      <ol className="dispatch-order">
                        {dispatch.entries.map((entry) => {
                          const mission = data.missions.find(
                            (m) => m.id === entry.mission_id,
                          );
                          const candidate = data.aircraft.find(
                            (a) => a.id === entry.aircraft_id,
                          );
                          const ready =
                            mission?.state === "requested" &&
                            mission.revision === entry.mission_revision &&
                            candidate?.status === "available" &&
                            !candidate.active_mission_id;
                          return (
                            <li key={entry.mission_id}>
                              <div>
                                <strong>{entry.label}</strong>
                                <p className="fine">
                                  {entry.aircraft_name} ·{" "}
                                  {new Date(
                                    entry.estimated_start * 1000,
                                  ).toLocaleTimeString()}
                                  –
                                  {new Date(
                                    entry.estimated_end * 1000,
                                  ).toLocaleTimeString()}{" "}
                                  · estimated battery after return{" "}
                                  {entry.estimated_battery_after}%
                                </p>
                                {entry.predecessor_id && (
                                  <p className="fine">
                                    Follows the preceding round trip on this
                                    aircraft; rebuild the preview after it
                                    returns.
                                  </p>
                                )}
                              </div>
                              {canOperate && (
                                <button
                                  disabled={
                                    busy || !ready || !!entry.predecessor_id
                                  }
                                  onClick={() => {
                                    if (mission) {
                                      setSelected(mission.id);
                                      void act(
                                        mission,
                                        "plan",
                                        entry.aircraft_id,
                                      );
                                    }
                                  }}
                                >
                                  Plan this delivery
                                </button>
                              )}
                            </li>
                          );
                        })}
                      </ol>
                      {!dispatch.entries.length && (
                        <p>No feasible assignments in this preview.</p>
                      )}
                      {dispatch.unassigned.map((entry) => (
                        <p className="fine" key={entry.mission_id}>
                          <strong>{entry.label}:</strong> {entry.reason}
                        </p>
                      ))}
                      {(dispatch.truncated.missions ||
                        dispatch.truncated.aircraft) && (
                        <p className="fine">
                          Preview considers up to 25 requests and 50 available
                          aircraft; additional records remain outside this
                          batch.
                        </p>
                      )}
                    </>
                  )}
                </section>
              )}
              <div className="operations-grid">
                <section>
                  <h2>
                    {page === "Delivery management"
                      ? "Delivery queue"
                      : "Missions"}
                  </h2>
                  <MissionList
                    missions={data.missions}
                    selected={flight?.id}
                    select={(m) => setSelected(m.id)}
                  />
                  {data.truncated.missions && (
                    <p>
                      Showing the latest 100 missions. Counts include all
                      records.
                    </p>
                  )}
                </section>
                <section className="mission-detail">
                  {flight ? (
                    <>
                      <div className="section-heading">
                        <h2>{flight.label}</h2>
                        <Badge state={flight.state} />
                      </div>
                      <p>
                        {flight.package_weight} kg · {flight.package_kind}{" "}
                        package · {human(flight.scenario)}
                      </p>
                      <dl className="detail-list">
                        <div>
                          <dt>Aircraft</dt>
                          <dd>{aircraft?.name || "Awaiting assignment"}</dd>
                        </div>
                        <div>
                          <dt>Round-trip distance</dt>
                          <dd>
                            {flight.plan.distance_m
                              ? distance(flight.plan.distance_m)
                              : "Unplanned"}
                          </dd>
                        </div>
                        <div>
                          <dt>Estimated duration</dt>
                          <dd>
                            {flight.plan.duration_min
                              ? `${flight.plan.duration_min} min`
                              : "Unplanned"}
                          </dd>
                        </div>
                        <div>
                          <dt>Estimated energy</dt>
                          <dd>
                            {flight.plan.energy_percent !== undefined
                              ? `${flight.plan.energy_percent}% + ${flight.plan.reserve_percent}% reserve`
                              : "Unplanned"}
                          </dd>
                        </div>
                        <div>
                          <dt>Scheduled</dt>
                          <dd>
                            {flight.scheduled_at
                              ? new Date(
                                  flight.scheduled_at * 1000,
                                ).toLocaleString()
                              : "On demand"}
                          </dd>
                        </div>
                        <div>
                          <dt>Delivered</dt>
                          <dd>
                            {flight.delivered
                              ? "Simulated confirmation recorded"
                              : "Pending"}
                          </dd>
                        </div>
                      </dl>
                      {canOperate && flight.state === "requested" && (
                        <label>
                          Route preference
                          <select
                            value={routeIndex}
                            onChange={(e) =>
                              setRouteIndex(Number(e.target.value))
                            }
                          >
                            <option value={0}>Shortest feasible route</option>
                            <option value={1}>Alternative route 1</option>
                            <option value={2}>Alternative route 2</option>
                          </select>
                          <span className="fine">
                            Alternatives are checked against the same virtual
                            restrictions and energy reserve. An unavailable
                            choice is rejected.
                          </span>
                        </label>
                      )}
                      {!!flight.plan.alternatives?.length && (
                        <div className="route-options">
                          <h3>Feasible route options</h3>
                          {flight.plan.alternatives.map((option) => (
                            <p className="fine" key={option.route_index}>
                              <strong>
                                {option.route_index === 0
                                  ? "Shortest route"
                                  : `Alternative ${option.route_index}`}
                                {option.route_index === flight.plan.route_index
                                  ? " · Selected"
                                  : ""}
                              </strong>
                              : {distance(option.distance_m)} ·{" "}
                              {option.duration_min} min ·{" "}
                              {option.energy_percent}% estimated energy
                            </p>
                          ))}
                          <p className="fine">
                            Release and replan to change routes. Preflight and
                            authorization must run again.
                          </p>
                        </div>
                      )}
                      {canOperate && (
                        <div className="actions mission-actions">
                          {(
                            {
                              requested: ["plan"],
                              planned: ["validate", "replan"],
                              validated: ["authorize", "replan"],
                              authorized: ["launch", "replan"],
                              paused: ["recover"],
                            }[flight.state] || []
                          ).map((action) => (
                            <button
                              className="primary"
                              disabled={busy}
                              key={action}
                              onClick={() => void act(flight, action)}
                            >
                              {
                                (
                                  {
                                    plan: "Plan & assign",
                                    validate: "Validate preflight",
                                    authorize: "Authorize simulation",
                                    launch: "Launch simulation",
                                    recover: "Recover to virtual home",
                                    replan: "Release & replan",
                                  } as Record<string, string>
                                )[action]
                              }
                            </button>
                          ))}
                          {!terminal.includes(flight.state) && (
                            <button
                              disabled={busy}
                              onClick={() => void act(flight, "cancel")}
                            >
                              Cancel mission
                            </button>
                          )}
                          {["planned", "validated", "authorized"].includes(
                            flight.state,
                          ) && (
                            <button
                              disabled={busy}
                              onClick={() =>
                                void run(async () => {
                                  await api(
                                    `/missions/${flight.id}/commands`,
                                    "POST",
                                    {
                                      action: "reschedule",
                                      revision: flight.revision,
                                      scheduled_at: Date.now() / 1000 + 300,
                                    },
                                    crypto.randomUUID(),
                                  );
                                  await refresh();
                                })
                              }
                            >
                              Reschedule +5 min
                            </button>
                          )}
                        </div>
                      )}
                      {flight.state === "authorized" && (
                        <p className="fine">
                          Simulation authorization expires at{" "}
                          {new Date(
                            (flight.authorized_until || 0) * 1000,
                          ).toLocaleTimeString()}
                          . All safety checks run again at launch.
                        </p>
                      )}
                      {flight.plan.advisories?.map((a) => (
                        <p className="fine" key={a}>
                          {a}
                        </p>
                      ))}
                      {history && (
                        <>
                          <h3>Mission events</h3>
                          <ol className="timeline">
                            {history.events.map((e) => (
                              <li key={e.id}>
                                <div>
                                  <strong>{human(e.state)}</strong>
                                  <time>
                                    {new Date(e.at * 1000).toLocaleTimeString()}
                                  </time>
                                </div>
                                <p>{e.detail.reason}</p>
                                <small>
                                  Correlation {e.correlation_id.slice(0, 16)}
                                </small>
                              </li>
                            ))}
                          </ol>
                        </>
                      )}
                    </>
                  ) : (
                    <Empty>Create a delivery request to begin.</Empty>
                  )}
                </section>
              </div>
              {telemetry && Object.keys(telemetry).length > 0 && (
                <>
                  <div className="section-heading">
                    <h2>
                      {replay !== null
                        ? "Historical replay"
                        : "Simulation telemetry"}
                    </h2>
                    <span>
                      Sequence {telemetry.seq} · {telemetry.simulation_seconds}{" "}
                      simulated seconds
                    </span>
                  </div>
                  <div className="metrics">
                    <Metric
                      label="Altitude"
                      value={distance(telemetry.altitude_m || 0)}
                      foot="Virtual AGL"
                    />
                    <Metric
                      label="Ground speed"
                      value={`${telemetry.ground_speed_mps || 0} m/s`}
                      foot={`Heading ${telemetry.heading || 0}°`}
                    />
                    <Metric
                      label="Battery"
                      value={`${(telemetry.battery_percent || 0).toFixed(1)}%`}
                      foot={`${telemetry.remaining_endurance_min || 0} min estimated`}
                    />
                    <Metric
                      label="Payload"
                      value={telemetry.payload_state || "aboard"}
                      foot={telemetry.flight_mode || ""}
                    />
                  </div>
                  <TelemetryChart
                    samples={history?.telemetry || []}
                    title="Battery history"
                  />
                </>
              )}
              {history && history.telemetry.length > 0 && (
                <section className="replay">
                  <h3>Mission replay</h3>
                  <label>
                    Recorded sample
                    <input
                      type="range"
                      min="0"
                      max={history.telemetry.length - 1}
                      value={replay ?? history.telemetry.length - 1}
                      onChange={(e) => {
                        setReplay(+e.target.value);
                        setPlaying(false);
                      }}
                    />
                  </label>
                  <div className="actions">
                    <button
                      onClick={() => {
                        setReplay(0);
                        setPlaying(true);
                      }}
                    >
                      Play recorded telemetry
                    </button>
                    <button onClick={() => setPlaying(false)}>
                      Pause replay
                    </button>
                    <button
                      onClick={() => {
                        setReplay(null);
                        setPlaying(false);
                      }}
                    >
                      Return to current state
                    </button>
                  </div>
                  <p className="fine">
                    Retains up to {history.retention_samples} samples per
                    mission. Replay issues no mission commands.
                  </p>
                </section>
              )}
            </>
          )}
          {page === "Scenarios" && (
            <div className="scenario-list">
              {extra?.map((s: any, i: number) => (
                <article key={s.id}>
                  <span className="index">0{i + 1}</span>
                  <div>
                    <h2>{s.name}</h2>
                    <p>{s.description}</p>
                  </div>
                  {canOperate && (
                    <button
                      onClick={() => {
                        setModal("delivery");
                        sessionStorage.setItem("drone-scenario", s.id);
                      }}
                    >
                      Create scenario
                    </button>
                  )}
                </article>
              ))}
            </div>
          )}
          {page === "AI assistant" && (
            <section className="assistant">
              <div className="assistant-symbol">✧</div>
              <h2>Understand your operations.</h2>
              <p>
                Ask about mission plans, fleet condition or failed simulations.
                The assistant has read-only, tenant-filtered context.
              </p>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  const f = new FormData(e.currentTarget);
                  void run(async () => {
                    const r = await api<{
                      answer: string;
                      source: string;
                      provider_status: string;
                      provenance?: { provider: string; model: string };
                    }>("/assistant", "POST", { question: f.get("question") });
                    setAnswer(r.answer);
                    setExtra({ page, value: r });
                  });
                }}
              >
                <label>
                  Your question
                  <textarea
                    name="question"
                    maxLength={2000}
                    minLength={2}
                    required
                    placeholder="Explain the current mission and any safety concerns…"
                  />
                </label>
                <button className="primary" disabled={busy}>
                  {busy ? "Reviewing context…" : "Ask assistant"}
                </button>
              </form>
              {answer && (
                <article className="assistant-answer">
                  <Badge state="advisory only" />
                  <p>{answer}</p>
                  <small>
                    Source: {extra?.source} · Provider: {extra?.provider_status}
                    {extra?.provenance && (
                      <> · Model: {extra.provenance.model}</>
                    )}
                  </small>
                </article>
              )}
              <p className="fine">
                The local operational summary works without an AI provider. An
                administrator must configure an approved AI connection.
                Recommendations cannot authorize a mission.
              </p>
            </section>
          )}
          {page === "Analytics" && (
            <>
              <div className="metrics">
                <Metric
                  label="Total missions"
                  value={Object.values(data.counts).reduce((a, b) => a + b, 0)}
                  foot="All persisted mission records"
                />
                <Metric
                  label="Completed"
                  value={data.counts.completed || 0}
                  foot="Returned to virtual home"
                />
                <Metric
                  label="Aborted"
                  value={data.counts.aborted || 0}
                  foot="Safety or recovery outcomes"
                />
                <Metric
                  label="Cancelled"
                  value={data.counts.cancelled || 0}
                  foot="Operator cancellation"
                />
              </div>
              <section>
                <h2>Mission state distribution</h2>
                {Object.entries(data.counts).length ? (
                  Object.entries(data.counts).map(([state, count]) => (
                    <div className="distribution" key={state}>
                      <span>{human(state)}</span>
                      <meter
                        max={Math.max(...Object.values(data.counts), 1)}
                        value={count}
                        aria-label={human(state)}
                      />
                      <strong>{count}</strong>
                    </div>
                  ))
                ) : (
                  <Empty>
                    Complete a simulated delivery to build operational evidence.
                  </Empty>
                )}
              </section>
              <section className="report">
                <h2>Operational report</h2>
                <p>
                  Export aggregate simulation counts and the latest 100 mission
                  outcomes. Contains synthetic operational identifiers. No
                  customer address or tracking capability is exported.
                </p>
                <button
                  onClick={() => {
                    const blob = new Blob(
                      [
                        JSON.stringify(
                          {
                            mode: "simulation",
                            generated_at: new Date().toISOString(),
                            counts: data.counts,
                            missions: data.missions.map((m) => ({
                              id: m.id,
                              state: m.state,
                              scenario: m.scenario,
                              delivered: m.delivered,
                            })),
                          },
                          null,
                          2,
                        ),
                      ],
                      { type: "application/json" },
                    );
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement("a");
                    a.href = url;
                    a.download = "onesa-simulation-report.json";
                    a.click();
                    setTimeout(() => URL.revokeObjectURL(url), 1000);
                  }}
                >
                  Download report
                </button>
              </section>
            </>
          )}
          {page === "Cybersecurity" && extra && (
            <>
              <h2>Enforced boundaries</h2>
              <dl className="control-list">
                {Object.entries(extra.controls).map(([name, value]) => (
                  <div key={name}>
                    <dt>{human(name)}</dt>
                    <dd>{String(value)}</dd>
                  </div>
                ))}
              </dl>
              <div className="two-col">
                <section>
                  <h2>Incident reporting</h2>
                  {canOperate && (
                    <form
                      onSubmit={(e) => {
                        e.preventDefault();
                        const form = e.currentTarget;
                        const f = new FormData(form);
                        void run(async () => {
                          await api("/incidents", "POST", {
                            title: f.get("title"),
                            detail: f.get("detail"),
                          });
                          setExtra({ page, value: await api("/security") });
                          form.reset();
                        });
                      }}
                    >
                      <label>
                        Title
                        <input
                          name="title"
                          minLength={3}
                          maxLength={100}
                          required
                        />
                      </label>
                      <label>
                        Details
                        <textarea
                          name="detail"
                          minLength={3}
                          maxLength={1000}
                          required
                        />
                      </label>
                      <button disabled={busy}>Record incident</button>
                    </form>
                  )}
                  {extra.incidents.map((i: any) => (
                    <article className="incident" key={i.id}>
                      <h3>{i.title}</h3>
                      <p>{i.detail}</p>
                      <Badge state={i.state} />
                      {canOperate && i.state !== "resolved" && (
                        <button
                          disabled={busy}
                          onClick={() =>
                            void run(async () => {
                              await api(`/incidents/${i.id}`, "PUT", {
                                state: "resolved",
                              });
                              setExtra({ page, value: await api("/security") });
                            })
                          }
                        >
                          Resolve
                        </button>
                      )}
                    </article>
                  ))}
                </section>
                <section>
                  <h2>Durable audit journal</h2>
                  <ol className="timeline">
                    {extra.audit.map((a: any) => (
                      <li key={a.id}>
                        <strong>{human(a.action)}</strong>
                        <p>{new Date(a.at * 1000).toLocaleString()}</p>
                        <small>
                          Correlation {a.correlation_id.slice(0, 20)} · SHA256{" "}
                          {a.digest.slice(0, 12)}…
                        </small>
                      </li>
                    ))}
                  </ol>
                </section>
              </div>
            </>
          )}
          {page === "Flight plans" && (
            <FlightPlanPreview key={`${user.id}:${user.tenant_id}`} />
          )}
          {page === "Infrastructure monitor" && extra && (
            <>
              <div className="service-list">
                {extra.services.map((s: any) => (
                  <div key={s.name}>
                    <Icon name={s.name} />
                    <div>
                      <h2>{s.name}</h2>
                      <p>{s.detail}</p>
                    </div>
                    <Badge state={s.status} />
                  </div>
                ))}
              </div>
              <div className="metrics">
                <Metric
                  label="API requests"
                  value={extra.metrics.requests}
                  foot="Current process"
                />
                <Metric
                  label="Uptime"
                  value={`${extra.metrics.uptime_seconds}s`}
                  foot="Current backend process"
                />
                <Metric
                  label="Worker failures"
                  value={extra.metrics.worker_failures}
                  foot="Consecutive storage failures"
                />
                <Metric
                  label="Telemetry retention"
                  value={extra.policy.retention_samples_per_mission}
                  foot="Samples per mission"
                />
                <Metric
                  label="Peak backend memory"
                  value={`${(extra.metrics.peak_rss_bytes / 1048576).toFixed(1)} MiB`}
                  foot="Process peak resident memory"
                />
                <Metric
                  label="Backend CPU"
                  value={`${extra.metrics.cpu_seconds}s`}
                  foot="Process user + system CPU time"
                />
              </div>
              <button
                disabled={busy}
                onClick={() =>
                  void run(async () =>
                    setExtra({ page, value: await api("/infrastructure") }),
                  )
                }
              >
                Refresh observations
              </button>
              <p className="fine">
                Hosted provider health and frontend deployment are not inferred
                from this page. No internal hostnames, credentials or database
                connection details are exposed.
              </p>
            </>
          )}
          {page === "Administration" &&
            (user.role === "admin" ? (
              <div className="two-col">
                <section>
                  <h2>Operating preferences</h2>
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      const f = new FormData(e.currentTarget);
                      void run(async () => {
                        const p = await api<Preferences>(
                          "/settings",
                          "PUT",
                          Object.fromEntries(f),
                        );
                        setPrefs(p);
                        setNotice("Operating preferences saved.");
                      });
                    }}
                  >
                    <label>
                      Currency
                      <select name="currency" defaultValue={prefs.currency}>
                        {["EUR", "USD", "ZAR", "NAD", "BWP", "ZMW", "GBP"].map(
                          (x) => (
                            <option key={x}>{x}</option>
                          ),
                        )}
                      </select>
                    </label>
                    <label>
                      Measurements
                      <select name="units" defaultValue={prefs.units}>
                        <option value="metric">Metric</option>
                        <option value="imperial">Imperial</option>
                      </select>
                    </label>
                    <label>
                      Report language
                      <select name="language" defaultValue={prefs.language}>
                        <option value="en">English</option>
                        <option value="de">Deutsch</option>
                      </select>
                    </label>
                    <label>
                      Operating region
                      <input
                        name="region"
                        defaultValue={prefs.region}
                        maxLength={80}
                        minLength={2}
                        required
                      />
                    </label>
                    <div className="form-grid">
                      <label>
                        Virtual radius (m)
                        <input
                          name="virtual_radius_m"
                          type="number"
                          min="100"
                          max="3000"
                          defaultValue={prefs.virtual_radius_m || 3000}
                          required
                        />
                      </label>
                      <label>
                        Synthetic wind (m/s)
                        <input
                          name="wind_mps"
                          type="number"
                          min="0"
                          max="30"
                          defaultValue={prefs.wind_mps ?? 5}
                          required
                        />
                      </label>
                      <label>
                        Battery reserve (%)
                        <input
                          name="reserve_percent"
                          type="number"
                          min="25"
                          max="80"
                          defaultValue={prefs.reserve_percent || 25}
                          required
                        />
                      </label>
                      <label>
                        Virtual altitude (m)
                        <input
                          name="altitude_m"
                          type="number"
                          min="10"
                          max="100"
                          defaultValue={prefs.altitude_m || 60}
                          required
                        />
                      </label>
                    </div>
                    <button className="primary" disabled={busy}>
                      Save preferences
                    </button>
                  </form>
                  <p className="fine">
                    Region preferences are labels; they do not load aviation
                    rules. Console translation and validated regional rule packs
                    remain in development.
                  </p>
                </section>
                <section>
                  <h2>Tenant access</h2>
                  {extra?.map((u: any) => (
                    <div className="user-row" key={u.id}>
                      <span>
                        {u.email}
                        <small>
                          {u.role} · {u.active ? "active" : "disabled"}
                        </small>
                      </span>
                      {u.id !== user.id && u.active && (
                        <button
                          onClick={() =>
                            void run(async () => {
                              await api(`/users/${u.id}/disable`, "POST", {});
                              setExtra({ page, value: await api("/users") });
                            })
                          }
                        >
                          Disable
                        </button>
                      )}
                    </div>
                  ))}
                  <h3>Provision an individual account</h3>
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      const form = e.currentTarget;
                      const f = new FormData(form);
                      void run(async () => {
                        await api("/users", "POST", Object.fromEntries(f));
                        setExtra({ page, value: await api("/users") });
                        form.reset();
                      });
                    }}
                  >
                    <label>
                      Email
                      <input
                        name="email"
                        type="email"
                        required
                        maxLength={160}
                      />
                    </label>
                    <label>
                      Initial password
                      <input
                        name="password"
                        type="password"
                        required
                        minLength={14}
                        maxLength={200}
                        autoComplete="new-password"
                      />
                    </label>
                    <label>
                      Role
                      <select name="role">
                        <option value="viewer">Viewer</option>
                        <option value="operator">Operator</option>
                        <option value="admin">Administrator</option>
                      </select>
                    </label>
                    <button disabled={busy}>Create account</button>
                  </form>
                </section>
              </div>
            ) : (
              <Empty>
                Administrator access is required to manage users and operating
                preferences.
              </Empty>
            ))}
          <footer className="console-footer">
            <span>ONESA DRONE · DEVELOPMENT RELEASE 0.1</span>
            <span>SIMULATED DATA · NO FLIGHT CERTIFICATION</span>
          </footer>
        </main>
      </div>
      {modal && (
        <Modal
          title={
            modal === "aircraft"
              ? edit
                ? "Edit illustrative aircraft"
                : "Register simulated aircraft"
              : "New simulated delivery"
          }
          close={() => {
            setModal(null);
            setEdit(null);
          }}
        >
          {modal === "aircraft" ? (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const f = new FormData(e.currentTarget);
                const body = {
                  name: f.get("name"),
                  model: f.get("model"),
                  manufacturer: f.get("manufacturer"),
                  category: f.get("category"),
                  capacity: Number(f.get("capacity")),
                  endurance: Number(f.get("endurance")),
                };
                void run(async () => {
                  await api(
                    edit
                      ? `/aircraft/${edit.id}?revision=${edit.revision}`
                      : "/aircraft",
                    edit ? "PUT" : "POST",
                    body,
                    crypto.randomUUID(),
                  );
                  await refresh();
                  setModal(null);
                  setEdit(null);
                });
              }}
            >
              <p>
                Configurations are illustrative. Enter no certified performance
                claims.
              </p>
              <label>
                Aircraft identifier
                <input
                  name="name"
                  required
                  minLength={2}
                  maxLength={40}
                  defaultValue={
                    edit?.name ||
                    `SIM-${String(data.aircraft.length + 1).padStart(3, "0")}`
                  }
                />
              </label>
              <label>
                Model
                <input
                  name="model"
                  required
                  maxLength={80}
                  defaultValue={edit?.model || "Campus delivery reference"}
                />
              </label>
              <label>
                Manufacturer / reference origin
                <input
                  name="manufacturer"
                  required
                  maxLength={80}
                  defaultValue={
                    edit?.manufacturer || "Onesa simulation reference"
                  }
                />
              </label>
              <div className="form-grid">
                <label>
                  Category
                  <select
                    name="category"
                    defaultValue={edit?.category || "multirotor"}
                  >
                    <option value="multirotor">Multirotor</option>
                    <option value="vtol">VTOL</option>
                    <option value="fixed-wing">Fixed-wing (viewer only)</option>
                  </select>
                </label>
                <label>
                  Payload capacity (kg)
                  <input
                    name="capacity"
                    type="number"
                    min="0.1"
                    max="100"
                    step="0.1"
                    required
                    defaultValue={edit?.capacity || 4}
                  />
                </label>
                <label>
                  Endurance (min)
                  <input
                    name="endurance"
                    type="number"
                    min="5"
                    max="240"
                    required
                    defaultValue={edit?.endurance || 35}
                  />
                </label>
              </div>
              <button className="primary" disabled={busy}>
                Save aircraft
              </button>
            </form>
          ) : (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const f = new FormData(e.currentTarget);
                void run(async () => {
                  const r = await api<{
                    mission: Mission;
                    tracking_token: string;
                  }>(
                    "/missions",
                    "POST",
                    {
                      label: f.get("label"),
                      package_weight: Number(f.get("weight")),
                      package_kind: f.get("kind"),
                      origin: {
                        lat: Number(f.get("origin_lat")),
                        lon: Number(f.get("origin_lon")),
                      },
                      destination: {
                        lat: Number(f.get("lat")),
                        lon: Number(f.get("lon")),
                      },
                      scenario: f.get("scenario"),
                      scheduled_at: f.get("schedule")
                        ? new Date(String(f.get("schedule"))).getTime() / 1000
                        : null,
                    },
                    crypto.randomUUID(),
                  );
                  setSelected(r.mission.id);
                  setTrack(`${location.origin}/track/${r.tracking_token}`);
                  await refresh();
                  setModal(null);
                  navigate("Mission control");
                  sessionStorage.removeItem("drone-scenario");
                });
              }}
            >
              <label>
                Delivery reference
                <input
                  name="label"
                  minLength={2}
                  maxLength={100}
                  required
                  placeholder="Campus medical supplies"
                />
              </label>
              <div className="form-grid">
                <label>
                  Weight (kg)
                  <input
                    name="weight"
                    type="number"
                    min="0.1"
                    max="100"
                    step="0.1"
                    defaultValue="1.2"
                    required
                  />
                </label>
                <label>
                  Package
                  <select name="kind">
                    <option value="standard">Standard</option>
                    <option value="medical">Medical (illustrative)</option>
                    <option value="fragile">Fragile (illustrative)</option>
                  </select>
                </label>
              </div>
              <p className="fine">
                Coordinates define an arbitrary virtual campus. The synthetic
                restriction is relative to home, independent of geography.
              </p>
              <div className="form-grid">
                <label>
                  Home latitude
                  <input
                    type="number"
                    step="any"
                    min="-85"
                    max="85"
                    name="origin_lat"
                    defaultValue="52.52"
                    required
                  />
                </label>
                <label>
                  Home longitude
                  <input
                    type="number"
                    step="any"
                    min="-180"
                    max="180"
                    name="origin_lon"
                    defaultValue="13.405"
                    required
                  />
                </label>
                <label>
                  Destination latitude
                  <input
                    type="number"
                    step="any"
                    min="-85"
                    max="85"
                    name="lat"
                    defaultValue="52.523"
                    required
                  />
                </label>
                <label>
                  Destination longitude
                  <input
                    type="number"
                    step="any"
                    min="-180"
                    max="180"
                    name="lon"
                    defaultValue="13.411"
                    required
                  />
                </label>
              </div>
              <label>
                Scenario
                <select
                  name="scenario"
                  defaultValue={
                    sessionStorage.getItem("drone-scenario") || "nominal"
                  }
                >
                  {[
                    "nominal",
                    "low_battery",
                    "communication_loss",
                    "gps_degradation",
                    "weather",
                    "obstruction",
                    "aircraft_fault",
                  ].map((s) => (
                    <option key={s} value={s}>
                      {human(s)}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Earliest launch (optional)
                <input name="schedule" type="datetime-local" />
              </label>
              <button className="primary" disabled={busy}>
                Register delivery
              </button>
            </form>
          )}
          {notice && (
            <p className="error" role="alert">
              {notice}
            </p>
          )}
        </Modal>
      )}
      {track && (
        <Modal title="Delivery tracking link" close={() => setTrack("")}>
          <p>
            This private read-only link expires in seven days. Share only with
            the intended recipient. It exposes simulation progress without a
            route, customer address or aircraft identity.
          </p>
          <label>
            Private tracking link
            <input readOnly value={track} onFocus={(e) => e.target.select()} />
          </label>
          <div className="actions">
            <button
              onClick={() =>
                void navigator.clipboard
                  .writeText(track)
                  .then(() => setNotice("Tracking link copied."))
                  .catch(() => setNotice("Select and copy the link manually."))
              }
            >
              Copy link
            </button>
            <button className="primary" onClick={() => setTrack("")}>
              Continue to mission
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
function Metric({
  label,
  value,
  foot,
}: {
  label: string;
  value: string | number;
  foot: string;
}) {
  return (
    <div className="metric">
      <p>{label}</p>
      <strong>{value}</strong>
      <small>{foot}</small>
    </div>
  );
}
function MissionList({
  missions,
  selected,
  select,
}: {
  missions: Mission[];
  selected?: string;
  select: (m: Mission) => void;
}) {
  return missions.length ? (
    <div className="mission-list">
      {missions.map((m) => (
        <button
          className={selected === m.id ? "mission-row selected" : "mission-row"}
          key={m.id}
          onClick={() => select(m)}
        >
          <span className="route-symbol" aria-hidden="true">
            ↗
          </span>
          <span>
            <strong>{m.label}</strong>
            <small>
              {m.package_weight} kg · {m.package_kind} · {m.id.slice(0, 8)}
            </small>
          </span>
          <Badge state={m.state} />
        </button>
      ))}
    </div>
  ) : (
    <Empty>
      No missions yet. Register a delivery to plan your first virtual flight.
    </Empty>
  );
}
function TelemetryChart({
  samples,
  title,
}: {
  samples: Sample[];
  title: string;
}) {
  if (!samples.length) return null;
  const points = samples
    .map(
      (s, i) =>
        `${(i / Math.max(samples.length - 1, 1)) * 900},${160 - s.battery_percent * 1.4}`,
    )
    .join(" ");
  return (
    <figure className="chart">
      <figcaption>{title} · simulation samples</figcaption>
      <svg
        role="img"
        aria-label={`${title}: ${samples.length} samples, last battery ${samples.at(-1)?.battery_percent}%`}
        viewBox="0 0 900 180"
        preserveAspectRatio="none"
      >
        <path
          d="M0 20h900M0 90h900M0 160h900"
          stroke="var(--onesa-divider)"
          fill="none"
        />
        <polyline
          points={points}
          fill="none"
          stroke="var(--onesa-accent)"
          strokeWidth="3"
        />
      </svg>
    </figure>
  );
}
function Modal({
  title,
  close,
  children,
}: {
  title: string;
  close: () => void;
  children: ReactNode;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const node = dialog.current;
    const previous = document.activeElement as HTMLElement | null;
    node?.showModal();
    return () => {
      node?.close();
      previous?.focus();
    };
  }, []);
  return (
    <dialog ref={dialog} onCancel={close} aria-labelledby="modal-title">
      <div className="modal-heading">
        <h2 id="modal-title">{title}</h2>
        <button className="quiet" aria-label="Close dialog" onClick={close}>
          ✕
        </button>
      </div>
      {children}
    </dialog>
  );
}
function Tracking({ token }: { token: string }) {
  const [data, setData] = useState<any>(null),
    [error, setError] = useState("");
  useEffect(() => {
    let stopped = false;
    const read = () =>
      api("/tracking/" + encodeURIComponent(token))
        .then((d) => {
          if (!stopped) setData(d);
        })
        .catch((e) => {
          if (!stopped) setError(e.message);
        });
    void read();
    const id = setInterval(() => void read(), 10000);
    return () => {
      stopped = true;
      clearInterval(id);
    };
  }, [token]);
  return (
    <main className="tracking">
      <span className="wordmark">
        ONESA <small>DRONE</small>
      </span>
      <p className="eyebrow">PRIVATE DELIVERY TRACKING / SIMULATION</p>
      <h1>
        Your virtual delivery,
        <br />
        at a glance.
      </h1>
      {error ? (
        <p role="alert">{error}</p>
      ) : data ? (
        <>
          <Badge state={data.state} />
          <label>
            Simulation progress
            <progress max="100" value={data.progress_percent} />
            {data.progress_percent}%
          </label>
          <p>
            {data.delivered
              ? "Simulated delivery confirmed."
              : "Your simulated package is in the delivery workflow."}
          </p>
        </>
      ) : (
        <p>Loading delivery status…</p>
      )}
      <p className="fine">
        Development simulation. This page does not track a physical aircraft or
        an operational delivery service.
      </p>
    </main>
  );
}
const subtitles: Record<string, string> = {
  Aircraft: "Manage illustrative aircraft configurations and availability.",
  "Fleet health": "Inspect simulated readiness and energy reserves.",
  Maintenance: "Record inspections and review maintenance evidence.",
  "Mission control": "Plan, validate, authorize and follow virtual deliveries.",
  "Delivery management":
    "Coordinate package requests and simulated delivery outcomes.",
  "Route planning":
    "Deterministic routing within explicit virtual constraints.",
  "Flight plans": "Inspect controller plan files in a command-free workspace.",
  "Live telemetry":
    "Trace simulation observations and recorded mission history.",
  "3D simulator":
    "Explore a procedural campus and replay persisted virtual flights.",
  "Digital twins":
    "Inspect illustrative aircraft and their simulated operational state.",
  Scenarios: "Exercise deterministic failures and operator recovery.",
  "AI assistant": "Read-only operational explanations with bounded context.",
  Analytics: "Explore persisted outcomes and export a simulation report.",
  Cybersecurity: "Inspect enforced boundaries, audit records and incidents.",
  "Infrastructure monitor":
    "Actual service observations with explicit evidence limits.",
  Administration:
    "Manage scoped access and international operating preferences.",
};
createRoot(document.getElementById("root")!).render(<App />);
