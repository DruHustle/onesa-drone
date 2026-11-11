export type MobilePlatform = "ios" | "android";

// Only owner-reviewed store listings for the matching platform may be linked.
export function storeListing(platform: MobilePlatform, configured: unknown): string | null {
  if (typeof configured !== "string" || !configured) return null;
  try {
    const url = new URL(configured);
    if (url.protocol !== "https:" || url.username || url.password || url.port || url.hash) return null;
    if (platform === "android") {
      return url.hostname === "play.google.com" && url.pathname === "/store/apps/details" &&
        url.search === "?id=eu.onesa.drone" ? url.href : null;
    }
    return url.hostname === "apps.apple.com" && !url.search &&
      /^\/(?:[a-z]{2}\/)?app\/(?:[a-z0-9-]+\/)?id[1-9][0-9]{5,14}\/?$/i.test(url.pathname) ? url.href : null;
  } catch { return null; }
}
