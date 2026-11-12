# Drone frontend layout

- `drone/web/`: canonical React/Three.js web console source, config, tests, bundled public assets and independent package lock.
- `drone/mobile/`: Expo/React Native field-operations prototype with Android and iOS native targets.

The existing `frontend/` package, lockfile, Playwright config and Vercel settings are a deployment-compatibility entry point. They install the existing pinned web dependencies, execute the web tests from the new source tree, and write the built frontend to `frontend/dist/` so that the already-qualified release packager remains unchanged. Do not deploy the new mobile app from the web distribution.

Commands from `onesa-drone/`:

```bash
npm --prefix frontend ci --ignore-scripts
npm --prefix frontend run test:unit
npm --prefix frontend run typecheck
npm --prefix frontend run build
npm --prefix frontend run test:e2e
node scripts/check_frontend_release_package.mjs
```

Mobile:
```bash
cd frontend/drone/mobile
npm install
npm test
npx expo export --platform all
npm run ios      # requires macOS + Xcode
npm run android  # requires Android SDK
```

Hardware flight and external video relay are absent, not hidden behind a feature toggle. Physical operation remains blocked by the Onesa Drone simulation-only policy and requires separate authorization, device integration and safety qualification.

After building the web frontend from the repository root, run
`python -m scripts.check_hosted_favicons` to compare the production home and
tracking pages with the built favicon files. The read-only check requires no
account. The frontend release runner performs the same check against the
verified package on staging and production.
