import { useEffect, useRef, useState } from "react";
import * as T from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import type { Mission, Sample } from "./types";

type Props = {
  mission?: Mission;
  sample?: Partial<Sample>;
  lowPower: boolean;
  night: boolean;
  weather: boolean;
  view: string;
  category?: string;
};
export default function DroneScene(props: Props) {
  const host = useRef<HTMLDivElement>(null),
    current = useRef(props);
  current.current = props;
  const [failure, setFailure] = useState(false),
    [stats, setStats] = useState("Initializing scene…");
  useEffect(() => {
    const element = host.current;
    if (!element) return;
    let renderer: T.WebGLRenderer;
    try {
      renderer = new T.WebGLRenderer({
        antialias:
          !props.lowPower &&
          !matchMedia("(prefers-reduced-motion: reduce)").matches,
        alpha: false,
        powerPreference: "low-power",
      });
    } catch {
      setFailure(true);
      return;
    }
    const scene = new T.Scene(),
      camera = new T.PerspectiveCamera(44, 1, 0.1, 3000);
    camera.position.set(170, 140, 220);
    renderer.setPixelRatio(
      Math.min(devicePixelRatio, props.lowPower ? 1 : 1.25),
    );
    renderer.shadowMap.enabled =
      !props.lowPower &&
      !matchMedia("(prefers-reduced-motion: reduce)").matches;
    renderer.shadowMap.type = T.PCFShadowMap;
    element.appendChild(renderer.domElement);
    renderer.domElement.setAttribute(
      "aria-label",
      "Illustrative 3D drone and virtual campus",
    );
    renderer.domElement.setAttribute("role", "img");
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.minDistance = 12;
    controls.maxDistance = 700;
    controls.maxPolarAngle = Math.PI * 0.49;
    const ambient = new T.HemisphereLight(0xe6f5ff, 0x566a52, 2.5);
    scene.add(ambient);
    const sun = new T.DirectionalLight(0xfff5de, 3);
    sun.position.set(120, 240, 80);
    sun.castShadow = !props.lowPower;
    sun.shadow.mapSize.set(1024, 1024);
    sun.shadow.camera.left = -250;
    sun.shadow.camera.right = 250;
    sun.shadow.camera.top = 250;
    sun.shadow.camera.bottom = -250;
    scene.add(sun);
    const material = (color: number, metalness = 0.1, roughness = 0.65) =>
      new T.MeshStandardMaterial({ color, metalness, roughness });
    const ground = new T.Mesh(
      new T.PlaneGeometry(2000, 2000),
      material(0x849c8a),
    );
    ground.rotation.x = -Math.PI / 2;
    ground.receiveShadow = true;
    ground.position.y = -0.15;
    scene.add(ground);
    const grid = new T.GridHelper(1400, 56, 0xabc5bd, 0x91ada0);
    grid.position.y = 0.05;
    scene.add(grid);
    const roadMat = material(0x53676b);
    for (const x of [-240, 0, 240]) {
      const road = new T.Mesh(new T.BoxGeometry(18, 0.15, 1400), roadMat);
      road.position.set(x, 0.1, 0);
      scene.add(road);
      const cross = new T.Mesh(new T.BoxGeometry(1400, 0.15, 18), roadMat);
      cross.position.set(0, 0.1, x);
      scene.add(cross);
    }
    const buildings = new T.InstancedMesh(
      new T.BoxGeometry(1, 1, 1),
      material(0xb1c0c2),
      54,
    );
    buildings.castShadow = true;
    buildings.receiveShadow = true;
    const dummy = new T.Object3D();
    let i = 0;
    for (let x = -3; x <= 3; x++)
      for (let z = -3; z <= 3; z++)
        if (x !== 0 || z !== 0) {
          const h = 14 + ((x * x + z * z * 3) % 5) * 9;
          dummy.position.set(x * 95 + 38, h / 2, z * 90 + 32);
          dummy.scale.set(42, h, 32);
          dummy.updateMatrix();
          buildings.setMatrixAt(i++, dummy.matrix);
        }
    buildings.count = i;
    scene.add(buildings);
    const pad = new T.Mesh(
      new T.CylinderGeometry(18, 18, 0.4, 48),
      material(0x203c48),
    );
    pad.position.y = 0.25;
    scene.add(pad);
    const ring = new T.Mesh(
      new T.RingGeometry(13, 14, 48),
      new T.MeshBasicMaterial({ color: 0x63f0b5, side: T.DoubleSide }),
    );
    ring.rotation.x = -Math.PI / 2;
    ring.position.y = 0.5;
    scene.add(ring);
    for (const x of [-3, 3]) {
      const bar = new T.Mesh(new T.BoxGeometry(1, 0.2, 10), material(0xffffff));
      bar.position.set(x, 0.6, 0);
      scene.add(bar);
    }
    const middle = new T.Mesh(new T.BoxGeometry(6, 0.2, 1), material(0xffffff));
    middle.position.y = 0.6;
    scene.add(middle);
    const drone = new T.Group();
    drone.scale.setScalar(3.2);
    scene.add(drone);
    const body = new T.Mesh(
      new T.SphereGeometry(1.4, 32, 16),
      material(0xe4e9e9, 0.6, 0.25),
    );
    body.scale.set(1, 0.46, 1.4);
    body.castShadow = true;
    drone.add(body);
    const canopy = new T.Mesh(
      new T.SphereGeometry(0.9, 24, 12),
      material(0x172f3a, 0.7, 0.2),
    );
    canopy.scale.set(1, 0.5, 1.3);
    canopy.position.y = 0.35;
    drone.add(canopy);
    const arms = new T.Group();
    drone.add(arms);
    const propsGroups: T.Group[] = [];
    const gear: T.Mesh[] = [];
    for (const x of [-1, 1])
      for (const z of [-1, 1]) {
        const arm = new T.Mesh(
          new T.BoxGeometry(3.1, 0.2, 0.3),
          material(0x344951, 0.6),
        );
        arm.position.set(x * 1.15, 0, z * 1.15);
        arm.rotation.y = (-x * z * Math.PI) / 4;
        arms.add(arm);
        const motor = new T.Mesh(
          new T.CylinderGeometry(0.34, 0.3, 0.45, 16),
          material(0x263a42, 0.8),
        );
        motor.position.set(x * 2.2, 0.2, z * 2.2);
        drone.add(motor);
        const rotor = new T.Group();
        rotor.position.copy(motor.position);
        rotor.position.y += 0.3;
        const blade = new T.Mesh(
          new T.BoxGeometry(3, 0.045, 0.17),
          material(0x142f36, 0.4),
        );
        rotor.add(blade);
        const second = blade.clone();
        second.rotation.y = Math.PI / 2;
        rotor.add(second);
        drone.add(rotor);
        propsGroups.push(rotor);
        const light = new T.Mesh(
          new T.SphereGeometry(0.12, 8, 8),
          new T.MeshBasicMaterial({ color: x < 0 ? 0xf45d66 : 0x55e2ae }),
        );
        light.position.set(x * 2.2, 0.3, z * 2.2);
        drone.add(light);
      }
    for (const x of [-1, 1]) {
      const strut = new T.Mesh(
        new T.BoxGeometry(0.12, 1.1, 2.3),
        material(0x344951, 0.7),
      );
      strut.position.set(x * 0.9, -0.9, 0);
      drone.add(strut);
      gear.push(strut);
    }
    const parcel = new T.Mesh(
      new T.BoxGeometry(1.3, 0.8, 1),
      material(0xbb9061),
    );
    parcel.position.y = -0.9;
    drone.add(parcel);
    const wing = new T.Mesh(
      new T.BoxGeometry(8, 0.15, 1.2),
      material(0xdbe5e4, 0.5),
    );
    wing.position.z = 0.3;
    drone.add(wing);
    const lineMaterial = new T.LineBasicMaterial({ color: 0x00774e });
    let route: T.Line | undefined;
    let routeKey = "";
    const zoneMaterial = new T.MeshBasicMaterial({
      color: 0xf0a45c,
      transparent: true,
      opacity: 0.12,
      depthWrite: false,
    });
    const zones = new T.Group();
    scene.add(zones);
    const rainGeo = new T.BufferGeometry(),
      rainPoints = new Float32Array(180 * 3);
    for (let k = 0; k < rainPoints.length; k += 3) {
      rainPoints[k] = ((k * 17) % 700) - 350;
      rainPoints[k + 1] = k % 120;
      rainPoints[k + 2] = ((k * 31) % 700) - 350;
    }
    rainGeo.setAttribute("position", new T.BufferAttribute(rainPoints, 3));
    const rain = new T.Points(
      rainGeo,
      new T.PointsMaterial({ color: 0xb7d8e6, size: 1.4 }),
    );
    scene.add(rain);
    let dirty = true,
      signature = "",
      reported = false;
    controls.addEventListener("change", () => {
      dirty = true;
    });
    const resize = () => {
      dirty = true;
      camera.aspect = element.clientWidth / Math.max(element.clientHeight, 1);
      camera.updateProjectionMatrix();
      renderer.setSize(element.clientWidth, element.clientHeight, false);
    };
    const observer = new ResizeObserver(resize);
    observer.observe(element);
    resize();
    const sceneStarted = performance.now();
    let frame = 0,
      frames = 0,
      last = performance.now(),
      lastDraw = 0,
      disposed = false;
    const initialized = performance.now();
    let firstFrame: number | undefined;
    const render = (now: number) => {
      if (disposed) return;
      frame = requestAnimationFrame(render);
      const p = current.current;
      const low = p.lowPower;
      const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
      const m = p.mission,
        s = p.sample || m?.last_telemetry || {};
      const active =
        !!m &&
        [
          "taking_off",
          "outbound",
          "returning",
          "landing",
          "delivering",
        ].includes(m.state);
      const continuous = !reduced && (active || p.weather);
      const nextSignature = JSON.stringify([
        m?.id,
        m?.state,
        m?.tick,
        m?.plan.waypoints,
        s.seq,
        p.lowPower,
        p.night,
        p.weather,
        p.view,
        p.category,
      ]);
      if (nextSignature !== signature) {
        dirty = true;
        signature = nextSignature;
      }
      if (!continuous && !dirty) return;
      const shadows = !low && !reduced;
      if (renderer.shadowMap.enabled !== shadows) {
        renderer.shadowMap.enabled = shadows;
        renderer.setPixelRatio(Math.min(devicePixelRatio, low ? 1 : 1.25));
      }
      if (
        document.hidden ||
        now - lastDraw < (low || reduced ? 1000 / 24 : 1000 / 60)
      )
        return;
      lastDraw = now;
      dirty = false;
      const t = (performance.now() - sceneStarted) / 1000,
        home = m?.origin || { lat: 0, lon: 0 };
      const project = (v: { lat: number; lon: number }) =>
        new T.Vector3(
          (v.lon - home.lon) * 111320 * Math.cos((home.lat * Math.PI) / 180),
          0.8,
          -(v.lat - home.lat) * 111320,
        );
      const key = JSON.stringify([m?.id, m?.plan.waypoints]);
      if (key !== routeKey) {
        routeKey = key;
        if (route) {
          scene.remove(route);
          route.geometry.dispose();
        }
        zones.clear();
        if (m?.plan.waypoints) {
          const points = m.plan.waypoints.map(project);
          route = new T.Line(
            new T.BufferGeometry().setFromPoints(points.map((v) => v.setY(2))),
            lineMaterial,
          );
          scene.add(route);
          for (const z of m.plan.zones || []) {
            const area = new T.Mesh(
              new T.CylinderGeometry(z.radius, z.radius, 90, 32),
              zoneMaterial,
            );
            area.position.set(z.x, 45, -z.y);
            zones.add(area);
          }
        }
      }
      const target = s.position ? project(s.position) : new T.Vector3(0, 0, 0);
      target.y = (s.altitude_m || 0) + 5;
      if (reduced || !active) drone.position.copy(target);
      else drone.position.lerp(target, 0.12);
      drone.rotation.y = (-(s.heading || 0) * Math.PI) / 180;
      drone.rotation.z = reduced || !active ? 0 : Math.sin(t * 1.2) * 0.018;
      drone.rotation.x = reduced || !active ? 0 : Math.sin(t * 0.9) * 0.014;
      for (const rotor of propsGroups)
        rotor.rotation.y = reduced || !active ? 0 : t * 50;
      for (const strut of gear)
        strut.rotation.z = (s.altitude_m || 0) > 12 ? 0.45 : 0;
      parcel.visible = s.payload_state !== "delivered";
      if (m?.state === "delivering")
        parcel.position.y = -0.9 - Math.min(1, (m.tick % 4) / 3) * 1.8;
      wing.visible = p.category === "fixed-wing" || p.category === "vtol";
      arms.visible = p.category !== "fixed-wing";
      rain.visible = p.weather;
      rain.position.y = reduced ? 0 : -((t * 10) % 60);
      scene.background = new T.Color(p.night ? 0x0d1c2b : 0xc5dce1);
      scene.fog = new T.Fog(
        p.night ? 0x0d1c2b : 0xc5dce1,
        350,
        p.weather ? 650 : 1400,
      );
      ambient.intensity = p.night ? 0.65 : 2.5;
      sun.intensity = p.night ? 0.4 : 3;
      controls.enabled = p.view === "orbit";
      if (p.view === "inspect") {
        camera.position.lerp(
          drone.position.clone().add(new T.Vector3(18, 12, 22)),
          0.12,
        );
        controls.target.copy(drone.position);
      } else if (p.view === "follow") {
        camera.position.lerp(
          drone.position.clone().add(new T.Vector3(70, 45, 90)),
          0.05,
        );
        controls.target.lerp(drone.position, 0.08);
      } else if (p.view === "first-person") {
        camera.position.copy(drone.position).add(new T.Vector3(0, 2, -2));
        controls.target
          .copy(drone.position)
          .add(
            new T.Vector3(
              Math.sin(drone.rotation.y) * 100,
              0,
              -Math.cos(drone.rotation.y) * 100,
            ),
          );
      }
      controls.update();
      renderer.render(scene, camera);
      firstFrame ??= performance.now() - initialized;
      frames++;
      if (!reported || now - last >= 2000) {
        reported = true;
        const fps = Math.round((frames * 1000) / (now - last));
        setStats(
          `${continuous ? `${fps} fps` : "on demand"} · ${renderer.info.render.triangles.toLocaleString()} triangles · ${renderer.info.memory.geometries} geometries · ready ${Math.round(firstFrame || 0)} ms`,
        );
        frames = 0;
        last = now;
      }
    };
    frame = requestAnimationFrame(render);
    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      observer.disconnect();
      controls.dispose();
      scene.traverse((o) => {
        const mesh = o as T.Mesh;
        if (mesh.geometry) mesh.geometry.dispose();
        if (mesh.material) {
          for (const m of Array.isArray(mesh.material)
            ? mesh.material
            : [mesh.material])
            m.dispose();
        }
      });
      renderer.dispose();
      renderer.forceContextLoss();
      renderer.domElement.remove();
    };
  }, []);
  return (
    <div className="scene-shell">
      <div ref={host} className="scene" />
      {failure && (
        <div className="scene-fallback">
          <strong>3D view unavailable</strong>
          <p>
            WebGL is unavailable. Mission controls and telemetry remain
            accessible below.
          </p>
        </div>
      )}
      <div className="scene-caption">
        <span>PROCEDURAL CAMPUS / ILLUSTRATIVE GEOMETRY</span>
        <span>{failure ? "WebGL unavailable" : stats}</span>
      </div>
    </div>
  );
}
