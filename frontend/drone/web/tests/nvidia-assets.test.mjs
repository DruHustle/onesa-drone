import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import { Box3, Vector3 } from "three";
import {
  referenceAssets,
  referenceUrl,
  validateReferenceGLB,
  loadReferenceAsset,
  disposeReferenceObject,
} from "../src/nvidiaAssets.ts";

const local = (path) =>
  new URL(`../public/models/nvidia/${path}`, import.meta.url);
const arrayBuffer = (bytes) =>
  bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);

test("the bundled application catalogue matches the public provenance catalogue", async () => {
  const published = JSON.parse(await readFile(local("manifest.json"), "utf8"));
  assert.deepEqual(referenceAssets, published.assets);
});

for (const asset of referenceAssets) {
  test(`${asset.name}: pinned provenance, complete files and actual GLTF geometry`, async (t) => {
    for (const entry of [
      asset.glb,
      asset.thumbnail,
      asset.licenseFile,
      asset.sourceFile,
    ]) {
      const bytes = await readFile(local(entry.path));
      assert.equal(bytes.length, entry.byteLength);
      assert.equal(
        createHash("sha256").update(bytes).digest("hex"),
        entry.sha256,
      );
    }
    const source = JSON.parse(
      await readFile(local(asset.sourceFile.path), "utf8"),
    );
    assert.equal(source.revision, asset.sourceRevision);
    assert.equal(source.assetId, asset.sourceAssetId);
    assert.equal(source.license, "CC-BY-4.0");
    const bytes = await readFile(local(asset.glb.path));
    t.mock.method(globalThis, "fetch", async (url, init) => {
      assert.equal(url, `/models/nvidia/${asset.glb.path}`);
      assert.equal(init.credentials, "same-origin");
      assert.equal(init.redirect, "error");
      assert.equal(init.headers, undefined);
      return new Response(bytes);
    });
    const model = await loadReferenceAsset(asset, new AbortController().signal);
    let triangles = 0;
    model.traverse((node) => {
      if (node.isMesh)
        triangles +=
          (node.geometry.index?.count ??
            node.geometry.attributes.position.count) / 3;
    });
    assert.equal(triangles, asset.triangles);
    const size = new Box3().setFromObject(model).getSize(new Vector3());
    assert.ok(
      size.toArray().every((value) => Number.isFinite(value) && value > 0),
    );
    disposeReferenceObject(model);
  });
}

test("corrupt, truncated and oversized downloads never become reference geometry", async (t) => {
  const asset = referenceAssets[0];
  const original = await readFile(local(asset.glb.path));
  const corrupted = Buffer.from(original);
  corrupted[corrupted.length - 1] ^= 1;
  for (const bytes of [
    corrupted,
    original.subarray(0, -1),
    Buffer.concat([original, Buffer.from([0])]),
  ]) {
    const mock = t.mock.method(
      globalThis,
      "fetch",
      async () => new Response(bytes),
    );
    await assert.rejects(
      loadReferenceAsset(asset, new AbortController().signal),
    );
    mock.mock.restore();
  }
});

test("an aborted request cannot finish a late parse", async (t) => {
  const asset = referenceAssets[0];
  const controller = new AbortController();
  const bytes = await readFile(local(asset.glb.path));
  t.mock.method(globalThis, "fetch", async () => {
    controller.abort();
    return new Response(bytes);
  });
  await assert.rejects(loadReferenceAsset(asset, controller.signal), {
    name: "AbortError",
  });
});

test("only catalogued relative paths can receive same-origin preview cookies", async (t) => {
  let requests = 0;
  t.mock.method(globalThis, "fetch", async () => {
    requests++;
    throw new Error("Unreviewed paths must fail before requesting");
  });
  for (const path of [
    "https://outside.invalid/model.glb",
    "//outside.invalid/model.glb",
    "../../api/v1/private",
    "%2e%2e/%2e%2e/private",
    referenceAssets[0].glb.path + "?redirect=outside",
    referenceAssets[0].glb.path + "#fragment",
    "nvidia-transfer-conveyor/unreviewed.glb",
  ]) {
    assert.throws(() => referenceUrl(path), /Unreviewed reference file/);
    await assert.rejects(loadReferenceAsset({
      ...referenceAssets[0], glb: { ...referenceAssets[0].glb, path },
    }, new AbortController().signal), /Unreviewed reference file/);
  }
  assert.equal(requests, 0);
});

test("the static reference profile rejects remote files, extensions and animation", () => {
  const encode = (extra) => {
    const json = Buffer.from(
      JSON.stringify({ asset: { version: "2.0" }, ...extra }),
    );
    const padded = Buffer.alloc(Math.ceil(json.length / 4) * 4, 32);
    json.copy(padded);
    const out = Buffer.alloc(20 + padded.length);
    out.writeUInt32LE(0x46546c67, 0);
    out.writeUInt32LE(2, 4);
    out.writeUInt32LE(out.length, 8);
    out.writeUInt32LE(padded.length, 12);
    out.writeUInt32LE(0x4e4f534a, 16);
    padded.copy(out, 20);
    return arrayBuffer(out);
  };
  for (const extra of [
    { buffers: [{ uri: "https://example.test/private.bin" }] },
    { images: [{ uri: "data:invalid" }] },
    { extensionsUsed: ["unknown"] },
    { animations: [{}] },
    { skins: [{}] },
  ])
    assert.throws(() => validateReferenceGLB(encode(extra)));
  assert.throws(() => validateReferenceGLB(new ArrayBuffer(5)));
});
