import MobileDownloads from "./MobileDownloads";
import { featureViews } from "./productEntry";

const features = [
  {
    id: "fleet",
    title: "Fleet",
    description: "Review simulated aircraft, availability and maintenance history.",
    example: "Demo aircraft D-14 is waiting for a battery inspection. The fleet view shows its maintenance status before it can be assigned.",
  },
  {
    id: "route",
    title: "Route planning",
    description: "Compare illustrative routes against the mission's operating constraints.",
    example: "A sample route is flagged for review because it reaches the destination with too little simulated battery reserve.",
  },
  {
    id: "simulation",
    title: "3D simulator",
    description: "Follow a simulated mission from take-off through its recorded outcome.",
    example: "A training mission stops before delivery and records a synthetic cancellation for the operator to review.",
  },
  {
    id: "telemetry",
    title: "Telemetry and replay",
    description: "Inspect simulated observations, mission history and connection status.",
    example: "A sample replay shows where an aircraft stopped reporting and keeps the last known reading labelled with its timestamp.",
  },
] as const satisfies ReadonlyArray<{
  id: keyof typeof featureViews;
  title: string;
  description: string;
  example: string;
}>;

export const droneRegistration =
  "https://account.onesa.eu/register?product=drone&platform=web";

export default function ProductOverview() {
  return (
    <main className="drone-overview">
      <header>
        <h1>Onesa Drone</h1>
        <p>Plan missions, manage a simulated fleet and review delivery operations.</p>
        <p>Flight, routes and telemetry in this product are simulated.</p>
        <nav aria-label="Onesa Drone account">
          <a href="/console">Sign in</a>
          <a href={droneRegistration + "&audience=user"}>Create an Onesa account</a>
        </nav>
      </header>
      <section aria-labelledby="drone-features">
        <h2 id="drone-features">Drone features</h2>
        <ul className="drone-overview-features">
          {features.map(feature => (
            <li key={feature.id}>
              <h3>{feature.title}</h3>
              <p>{feature.description}</p>
              <details>
                <summary>Synthetic example</summary>
                <p>{feature.example}</p>
              </details>
              <a href={`/console?view=${feature.id}`}>Open {feature.title}</a>
            </li>
          ))}
        </ul>
      </section>
      <MobileDownloads />
    </main>
  );
}
