import { createRequire } from "node:module";
import { resolve } from "node:path";
const p = process.env.PORTAL_ROOT;
const { build } = createRequire(
  resolve(p, "onesa-company-portal-backend/package.json"),
)("esbuild");
const front = resolve(p, "onesa-company-portal-frontend");
await build({
  stdin: {
    contents: `
      import {createRoot} from 'react-dom/client';
      import {OnesaAccount} from './src/features/account/account';
      import {AccountDeletion} from './src/features/account/deletion';
      const view = location.pathname === '/account/delete'
        ? <AccountDeletion />
        : <OnesaAccount interactionId={location.pathname.split('/')[3]} />;
      createRoot(document.getElementById('root')).render(view);
    `,
    loader: "tsx",
    resolveDir: front,
  },
  outfile: resolve("account.js"),
  absWorkingDir: front,
  tsconfig: resolve(front, "tsconfig.json"),
  jsx: "automatic",
  bundle: true,
  minify: true,
  platform: "browser",
  define: { "process.env.NODE_ENV": '"production"' },
});
await build({
  entryPoints: [resolve(front, "src/app/api/v1/[...path]/route.ts")],
  outfile: resolve("portal-proxy.cjs"),
  absWorkingDir: front,
  tsconfig: resolve(front, "tsconfig.json"),
  platform: "node",
  target: "node24",
  format: "cjs",
  bundle: true,
});
