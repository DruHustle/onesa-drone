import { useEffect, useId, useRef, useState } from "react";
import { api, SessionChangedError } from "./api";

type Preview = {
  mode: "offline-preview";
  source_sha256: string;
  firmware: string;
  horizontal_distance_m: number;
  virtual_radius_m: number;
  items: {
    sequence: number;
    command: string;
    command_id: number;
    frame: number;
    position: { lat: number; lon: number };
    relative_altitude_m: number | null;
    parameters: (number | null)[];
  }[];
  route: { sequence: number; x_m: number; y_m: number }[];
  zones: { x: number; y: number; radius: number; label: string }[];
  issues: { sequence: number; code: string; detail: string }[];
  notice: string;
};

function RouteGeometry({ preview }: { preview: Preview }) {
  const title = useId();
  const xs = preview.route.map((point) => point.x_m);
  const ys = preview.route.map((point) => point.y_m);
  const minX = Math.min(
    ...xs,
    ...preview.zones.map((zone) => zone.x - zone.radius - 20),
  );
  const maxX = Math.max(
    ...xs,
    ...preview.zones.map((zone) => zone.x + zone.radius + 20),
  );
  const minY = Math.min(
    ...ys,
    ...preview.zones.map((zone) => zone.y - zone.radius - 20),
  );
  const maxY = Math.max(
    ...ys,
    ...preview.zones.map((zone) => zone.y + zone.radius + 20),
  );
  const scale = Math.min(
    520 / Math.max(20, maxX - minX),
    230 / Math.max(20, maxY - minY),
  );
  const x = (value: number) => 40 + (value - minX) * scale;
  const y = (value: number) => 255 - (value - minY) * scale;
  const distinct = preview.route.filter(
    (point, index, route) =>
      route.findIndex(
        (other) => other.x_m === point.x_m && other.y_m === point.y_m,
      ) === index,
  );
  return (
    <svg
      className="flight-plan-map"
      viewBox="0 0 600 290"
      role="img"
      aria-labelledby={title}
    >
      <title id={title}>
        Imported route geometry, {preview.items.length} navigation items,{" "}
        {preview.horizontal_distance_m} metres horizontally
      </title>
      {preview.zones.map((zone) => (
        <circle
          key={zone.label}
          className="flight-plan-zone"
          cx={x(zone.x)}
          cy={y(zone.y)}
          r={(zone.radius + 20) * scale}
        />
      ))}
      <polyline
        points={preview.route
          .map((point) => `${x(point.x_m)},${y(point.y_m)}`)
          .join(" ")}
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
      />
      {distinct.map((point) => (
        <g key={point.sequence}>
          <circle
            cx={x(point.x_m)}
            cy={y(point.y_m)}
            r="4"
            fill="currentColor"
          />
          <text
            x={x(point.x_m) + 7}
            y={y(point.y_m) - 8}
            fill="currentColor"
            fontSize="12"
          >
            {point.sequence === 0 ? "H" : point.sequence}
          </text>
        </g>
      ))}
    </svg>
  );
}

export default function FlightPlanPreview() {
  const [source, setSource] = useState("");
  const [name, setName] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const generation = useRef(0);
  useEffect(
    () => () => {
      generation.current++;
    },
    [],
  );

  async function selectFile(file?: File) {
    const current = ++generation.current;
    setSource("");
    setName("");
    setPreview(null);
    setError("");
    setBusy(false);
    if (!file) return;
    if (
      !file.name.toLowerCase().endsWith(".plan") ||
      file.size === 0 ||
      file.size > 12 * 1024
    ) {
      setError("Choose a QGroundControl .plan file of at most 12 KiB.");
      return;
    }
    try {
      const text = new TextDecoder("utf-8", {
        fatal: true,
        ignoreBOM: true,
      }).decode(await file.arrayBuffer());
      if (current !== generation.current) return;
      setSource(text);
      setName(file.name);
    } catch {
      if (current === generation.current)
        setError("The selected file could not be read.");
    }
  }

  async function inspect() {
    const current = ++generation.current;
    setBusy(true);
    setPreview(null);
    setError("");
    try {
      const result = await api<Preview>("/flight-plans/preview", "POST", {
        source,
      });
      if (current === generation.current) setPreview(result);
    } catch (reason) {
      if (
        current === generation.current &&
        !(reason instanceof SessionChangedError)
      )
        setError(
          reason instanceof Error
            ? reason.message
            : "Plan preview unavailable.",
        );
    } finally {
      if (current === generation.current) setBusy(false);
    }
  }

  return (
    <section
      className="flight-plan-preview"
      aria-label="Flight controller plan compatibility"
    >
      <h2>Inspect a QGroundControl flight plan</h2>
      <p>
        Review a PX4 or ArduPilot multirotor route before developing a
        controller adapter. This read-only preview creates no mission and sends
        no aircraft commands.
      </p>
      <p className="fine">
        Supports takeoff, simple waypoints, then land or return to launch, with
        altitude relative to planned home. Survey patterns, imported geofences,
        rally points and other commands are rejected explicitly.
      </p>
      <label>
        QGroundControl .plan file
        <input
          type="file"
          accept=".plan,application/json"
          onChange={(event) => void selectFile(event.target.files?.[0])}
        />
      </label>
      <p className="fine">
        At most 12 KiB and 25 items. The file is inspected by this workspace’s
        API and is not saved. Use synthetic plans only.
      </p>
      <button
        className="primary"
        disabled={!source || busy}
        onClick={() => void inspect()}
      >
        {busy ? "Inspecting plan…" : "Preview flight plan"}
      </button>
      {error && <p role="alert">{error}</p>}
      {preview && (
        <div className="flight-plan-result" aria-live="polite">
          <h3>Offline preview · {preview.firmware}</h3>
          <p>
            {name} · {preview.items.length} items ·{" "}
            {preview.horizontal_distance_m.toLocaleString()} m horizontal route
            · {preview.virtual_radius_m.toLocaleString()} m virtual radius
          </p>
          <p>{preview.notice}</p>
          {preview.issues.length ? (
            <div>
              <h3>Virtual policy findings</h3>
              <ul>
                {preview.issues.map((issue, index) => (
                  <li key={`${issue.sequence}-${issue.code}-${index}`}>
                    Item {issue.sequence}: {issue.detail}
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p>
              No conflicts with the checked illustrative radius, zone or
              navigation-altitude rules. Battery, wind, real airspace and
              controller behavior remain unqualified.
            </p>
          )}
          <RouteGeometry preview={preview} />
          <p className="fine">
            North is up; east is right. H marks planned home. The dashed circle
            is an illustrative restriction with its clearance.
          </p>
          <ol className="flight-plan-items">
            {preview.items.map((item) => (
              <li key={item.sequence}>
                <strong>
                  {item.sequence}. {item.command.replaceAll("-", " ")}
                </strong>
                <span>
                  {item.position.lat.toFixed(6)}, {item.position.lon.toFixed(6)}{" "}
                  ·{" "}
                  {item.relative_altitude_m === null
                    ? "Return altitude: controller-defined"
                    : `${item.relative_altitude_m} m relative to planned home`}
                </span>
                <details>
                  <summary>Navigation parameters</summary>
                  <p>
                    MAV_CMD {item.command_id}, frame {item.frame}
                  </p>
                  <code>{JSON.stringify(item.parameters)}</code>
                </details>
              </li>
            ))}
          </ol>
          <p className="fine flight-plan-digest">
            Source SHA-256: <code>{preview.source_sha256}</code>
          </p>
        </div>
      )}
    </section>
  );
}
