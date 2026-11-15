export type MobilePlatform = "ios" | "android";

function cleanURL(value: unknown): URL | undefined {
  if (typeof value !== "string" || !value || value !== value.trim()) return;
  try {
    const url = new URL(value);
    if (url.protocol === "https:" && !url.username && !url.password && !url.port && !url.hash && url.href === value) return url;
  } catch { /* An unpublished or malformed destination stays unavailable. */ }
}

type ApkRelease = { url?: unknown; sha256?: unknown; certificateSha256?: unknown; sourceCommit?: unknown };

function apkLink(value: ApkRelease): string | null {
  const url = cleanURL(value.url);
  const hash = (entry: unknown) => typeof entry === "string" && /^[a-f0-9]{64}$/.test(entry);
  if (!url || url.search || !hash(value.sha256) || !hash(value.certificateSha256) ||
      typeof value.sourceCommit !== "string" || !/^[a-f0-9]{40}$/.test(value.sourceCommit)) return null;
  const version = "([0-9]+\\.[0-9]+\\.[0-9]+)";
  const asset = "onesa-drone-android-v" + version + "\\.apk";
  const github = new RegExp("^/DruHustle/onesa-drone/releases/download/mobile-v" + version + "/onesa-drone-android-v\\1\\.apk$");
  const product = new RegExp("^/downloads/" + asset + "$");
  if ((url.hostname === "github.com" && github.test(url.pathname)) ||
      (url.hostname === "drone.onesa.eu" && product.test(url.pathname))) return url.href;
  return null;
}

// Direct Android entries carry the hash and owner signing certificate from a verified release.
export function storeListing(platform: MobilePlatform, configured: unknown): string | null {
  if (platform === "android" && configured && typeof configured === "object" && !Array.isArray(configured)) {
    return apkLink(configured as ApkRelease);
  }
  const url = cleanURL(configured);
  if (!url) return null;
  if (platform === "android") {
    return url.hostname === "play.google.com" && url.pathname === "/store/apps/details" &&
      url.search === "?id=eu.onesa.drone" ? url.href : null;
  }
  if (url.search) return null;
  if (url.hostname === "testflight.apple.com" && /^\/join\/[a-zA-Z0-9]{8}$/.test(url.pathname)) return url.href;
  return url.hostname === "apps.apple.com" &&
    /^\/(?:[a-z]{2}\/)?app\/(?:[a-z0-9-]+\/)?id[1-9][0-9]{5,14}\/?$/i.test(url.pathname) ? url.href : null;
}
