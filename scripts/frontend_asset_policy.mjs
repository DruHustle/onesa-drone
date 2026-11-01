import { readFile } from "node:fs/promises";
import { createHash } from "node:crypto";

const sha = (bytes) => createHash("sha256").update(bytes).digest("hex");
const identifiers = new Set([
  "nvidia-transfer-conveyor",
  "nvidia-mobile-cart",
  "nvidia-storage-rack",
]);
const names = {
  glb: /^compact\.[a-f0-9]{16}\.glb$/,
  thumbnail: /^preview\.png$/,
  licenseFile: /^LICENSE\.txt$/,
  sourceFile: /^SOURCE\.json$/,
};

// The repository's compiled catalogue is trusted source, not a caller-supplied
// dist manifest. New reference identities require an explicit source review.
export async function requiredPublicFiles() {
  const catalogBytes = await readFile(
    new URL("../frontend/src/nvidia-manifest.json", import.meta.url),
  );
  const catalog = JSON.parse(catalogBytes);
  const required = new Map([
    ["models/nvidia/manifest.json", {
      byteLength: catalogBytes.length,
      sha256: sha(catalogBytes),
    }],
  ]);
  const seen = new Set();
  if (!Array.isArray(catalog.assets) || catalog.assets.length !== identifiers.size)
    throw new Error("Pinned NVIDIA catalogue is incomplete");
  for (const asset of catalog.assets) {
    if (!identifiers.has(asset.id) || seen.has(asset.id))
      throw new Error("Unreviewed or duplicate NVIDIA identity");
    seen.add(asset.id);
    for (const [key, pattern] of Object.entries(names)) {
      const file = asset[key];
      const parts = typeof file?.path === "string" ? file.path.split("/") : [];
      if (
        parts.length !== 2 || parts[0] !== asset.id || !pattern.test(parts[1]) ||
        !Number.isSafeInteger(file.byteLength) || file.byteLength <= 0 ||
        file.byteLength > 10 * 1024 * 1024 || !/^[a-f0-9]{64}$/.test(file.sha256)
      )
        throw new Error("Invalid pinned NVIDIA file reference");
      const path = "models/nvidia/" + file.path;
      if (required.has(path)) throw new Error("Duplicate pinned public file");
      required.set(path, { byteLength: file.byteLength, sha256: file.sha256 });
    }
  }
  const notice = await readFile(
    new URL("../frontend/public/licenses/three.txt", import.meta.url),
  );
  required.set("licenses/three.txt", {
    byteLength: notice.length,
    sha256: sha(notice),
  });
  return required;
}

export function assertPinnedBytes(path, bytes, expected) {
  if (bytes.length !== expected.byteLength || sha(bytes) !== expected.sha256)
    throw new Error("Pinned public artifact integrity mismatch: " + path);
}
