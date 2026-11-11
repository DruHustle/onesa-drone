import listings from "./mobile-downloads.json";
import { storeListing } from "./mobile-store-listing";

export default function MobileDownloads() {
  return (
    <section className="mobile-downloads" aria-label="Onesa Drone mobile downloads">
      <strong>Onesa Drone mobile app</strong>
      <ul>
        {(["ios", "android"] as const).map((platform) => {
          const label = platform === "ios" ? "iOS" : "Android";
          const href = storeListing(platform, listings[platform]);
          const icon = (
            <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24"
              fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 3v12m-5-5 5 5 5-5M4 16v4h16v-4" />
            </svg>
          );
          return <li key={platform}>
            {href ?
              <a href={href} aria-label={"Download Onesa Drone for " + label}>{icon}{label}</a> :
              <span>{icon}{label} · Unavailable</span>}
          </li>;
        })}
      </ul>
    </section>
  );
}
