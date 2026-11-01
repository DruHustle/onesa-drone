import * as T from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import manifest from "./nvidia-manifest.json" with { type: "json" };

export const referenceAssets = manifest.assets;
export type ReferenceAsset = (typeof referenceAssets)[number];
const referencePaths = new Set(referenceAssets.flatMap((asset) => [
  asset.glb.path, asset.thumbnail.path, asset.licenseFile.path, asset.sourceFile.path,
]));
export const referenceUrl = (path: string) => {
  if (!referencePaths.has(path)) throw new Error("Unreviewed reference file");
  return "/models/nvidia/" + path;
};

/** Only the checked, embedded static GLBs from the bundled catalogue are accepted. */
export function validateReferenceGLB(bytes: ArrayBuffer) {
  if (bytes.byteLength < 20) throw new Error("Incomplete reference model");
  const header = new DataView(bytes);
  const length = header.getUint32(12, true);
  if (
    header.getUint32(0, true) !== 0x46546c67 ||
    header.getUint32(4, true) !== 2 ||
    header.getUint32(8, true) !== bytes.byteLength ||
    header.getUint32(16, true) !== 0x4e4f534a ||
    length > bytes.byteLength - 20
  )
    throw new Error("Invalid reference model");
  const document = JSON.parse(
    new TextDecoder().decode(new Uint8Array(bytes, 20, length)),
  );
  if (
    document.asset?.version !== "2.0" ||
    document.animations?.length ||
    document.skins?.length ||
    document.extensionsUsed?.length ||
    document.extensionsRequired?.length ||
    (document.buffers || []).some(
      (v: { uri?: string }) => v.uri !== undefined,
    ) ||
    (document.images || []).some((v: { uri?: string }) => v.uri !== undefined)
  )
    throw new Error("Unsupported reference model");
}

export async function loadReferenceAsset(
  asset: ReferenceAsset,
  signal: AbortSignal,
) {
  const response = await fetch(referenceUrl(asset.glb.path), {
    signal,
    credentials: "same-origin",
    redirect: "error",
  });
  if (!response.ok || !response.body)
    throw new Error("Reference model unavailable");
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let length = 0;
  try {
    while (true) {
      const next = await reader.read();
      if (next.done) break;
      length += next.value.byteLength;
      if (length > asset.glb.byteLength) {
        await reader.cancel();
        throw new Error("Reference model exceeds its pinned size");
      }
      chunks.push(next.value);
    }
  } finally {
    reader.releaseLock();
  }
  if (length !== asset.glb.byteLength)
    throw new Error("Incomplete reference model");
  const bytes = new Uint8Array(length);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.length;
  }
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
  const hash = Array.from(digest, (v) => v.toString(16).padStart(2, "0")).join(
    "",
  );
  if (hash !== asset.glb.sha256)
    throw new Error("Reference model integrity check failed");
  signal.throwIfAborted();
  validateReferenceGLB(bytes.buffer);
  const loader = new GLTFLoader();
  const result = await loader.parseAsync(bytes.buffer, "");
  if (signal.aborted) {
    disposeReferenceObject(result.scene);
    signal.throwIfAborted();
  }
  return result.scene;
}

export function disposeReferenceObject(object: T.Object3D) {
  const geometries = new Set<T.BufferGeometry>();
  const materials = new Set<T.Material>();
  const textures = new Set<T.Texture>();
  object.traverse((node) => {
    const mesh = node as T.Mesh;
    if (mesh.geometry) geometries.add(mesh.geometry);
    if (!mesh.material) return;
    for (const material of Array.isArray(mesh.material)
      ? mesh.material
      : [mesh.material]) {
      materials.add(material);
      for (const value of Object.values(material))
        if (value instanceof T.Texture) textures.add(value);
    }
  });
  textures.forEach((texture) => texture.dispose());
  materials.forEach((material) => material.dispose());
  geometries.forEach((geometry) => geometry.dispose());
}
