import {
  mkdir,
  readdir,
  readFile,
  writeFile,
  copyFile,
  lstat,
} from "node:fs/promises";
import { resolve, relative, join, extname } from "node:path";
import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";

const origins = {
  staging: "https://drone-api-staging.onesa.eu",
  production: "https://drone-api.onesa.eu",
};
const allowed = new Set([
  ".html",
  ".js",
  ".css",
  ".svg",
  ".png",
  ".webp",
  ".ico",
  ".woff",
  ".woff2",
  ".txt",
]);
const sha = (bytes) => createHash("sha256").update(bytes).digest("hex");

export async function packageVercel({
  dist,
  output,
  environment,
  backendOrigin,
  sourceCommit,
  projectId,
  orgId,
}) {
  if (
    !Object.hasOwn(origins, environment) ||
    backendOrigin !== origins[environment]
  )
    throw new Error(
      "Release environment and approved backend origin must match",
    );
  if (
    !/^[a-f0-9]{40}$/.test(sourceCommit) ||
    !/^prj_[A-Za-z0-9]+$/.test(projectId) ||
    !/^[A-Za-z0-9_]{12,100}$/.test(orgId)
  )
    throw new Error("Observed project, team and full source identity required");
  dist = resolve(dist);
  output = resolve(output);
  if (
    output === dist ||
    output.startsWith(dist + "/") ||
    dist.startsWith(output + "/")
  )
    throw new Error(
      "Source and release output must be independent directories",
    );
  const files = [];
  let bytes = 0;
  async function walk(folder) {
    for (const entry of await readdir(folder, { withFileTypes: true })) {
      const path = join(folder, entry.name);
      const stat = await lstat(path);
      if (entry.name.startsWith(".") || stat.isSymbolicLink())
        throw new Error(
          "Hidden files and symlinks cannot enter a public artifact",
        );
      if (stat.isDirectory()) {
        await walk(path);
        continue;
      }
      if (
        !stat.isFile() ||
        !allowed.has(extname(entry.name)) ||
        stat.size > 10 * 1024 * 1024
      )
        throw new Error("Unexpected or oversized frontend artifact");
      bytes += stat.size;
      files.push({ path, name: relative(dist, path) });
      if (files.length > 1000 || bytes > 30 * 1024 * 1024)
        throw new Error("Frontend artifact exceeds bounded release size");
    }
  }
  await walk(dist);
  if (
    !files.some((file) => file.name === "index.html") ||
    !files.some((file) => file.name.endsWith(".js"))
  )
    throw new Error("A built frontend is required");
  // Refuse an existing directory, including a partial earlier attempt.
  await mkdir(output, { recursive: false });
  const vercel = join(output, ".vercel");
  const staticPath = join(vercel, "output", "static");
  await mkdir(staticPath, { recursive: true });
  const manifest = {
    environment,
    backend_origin: backendOrigin,
    source_commit: sourceCommit,
    project_id: projectId,
    org_id: orgId,
    bytes,
    files: {},
  };
  for (const file of files.sort((a, b) => a.name.localeCompare(b.name))) {
    const target = join(staticPath, file.name);
    await mkdir(resolve(target, ".."), { recursive: true });
    await copyFile(file.path, target);
    manifest.files[file.name] = sha(await readFile(target));
  }
  const config = {
    version: 3,
    routes: [
      {
        src: "/(.*)",
        headers: {
          "X-Content-Type-Options": "nosniff",
          "Referrer-Policy": "no-referrer",
          "X-Frame-Options": "DENY",
          "X-Robots-Tag": "noindex, nofollow, noarchive",
          "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
          "Content-Security-Policy":
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; font-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'",
        },
        continue: true,
      },
      {
        src: "/api/(.*)",
        dest: backendOrigin + "/api/$1",
        headers: { "Cache-Control": "no-store" },
      },
      {
        src: "/assets/(.*)",
        headers: { "Cache-Control": "public, max-age=31536000, immutable" },
        continue: true,
      },
      { handle: "filesystem" },
      {
        src: "/(.*)",
        dest: "/index.html",
        headers: { "Cache-Control": "no-cache" },
      },
    ],
  };
  const encoded = JSON.stringify(config, null, 2) + "\n";
  await writeFile(join(vercel, "output", "config.json"), encoded);
  await writeFile(
    join(vercel, "project.json"),
    JSON.stringify({ projectId, orgId, projectName: "onesa-drone" }) + "\n",
  );
  manifest.routing_sha256 = sha(encoded);
  await writeFile(
    join(output, "release.json"),
    JSON.stringify(manifest, null, 2) + "\n",
  );
  return manifest;
}

if (
  process.argv[1] &&
  resolve(process.argv[1]) === fileURLToPath(import.meta.url)
) {
  const [dist, output, environment, sourceCommit, projectId, orgId] =
    process.argv.slice(2);
  const result = await packageVercel({
    dist,
    output,
    environment,
    backendOrigin: origins[environment],
    sourceCommit,
    projectId,
    orgId,
  });
  console.log(
    JSON.stringify({
      environment: result.environment,
      source_commit: result.source_commit,
      files: Object.keys(result.files).length,
      bytes: result.bytes,
    }),
  );
}
