// Holloway viewer. Scene data arrives in holloway's z-up coordinates and is
// converted to three.js's y-up on load: (x, y, z) -> (x, z, -y).
import * as THREE from "three";

const $ = (id) => document.getElementById(id);
const toThree = ([x, y, z]) => new THREE.Vector3(x, z, -y);
const fromThree = (v) => [v.x, -v.z, v.y];

const store = {
  get(key, fallback) {
    try { const v = localStorage.getItem("holloway:" + key); return v === null ? fallback : JSON.parse(v); }
    catch { return fallback; }
  },
  set(key, value) { try { localStorage.setItem("holloway:" + key, JSON.stringify(value)); } catch {} },
};

// --- renderer, scene, camera -------------------------------------------------

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(window.devicePixelRatio);
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
document.body.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0xc4ccd2);

const camera = new THREE.PerspectiveCamera(70, window.innerWidth / window.innerHeight, 0.05, 5000);
camera.rotation.order = "YXZ";

window.addEventListener("resize", () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

// --- lights --------------------------------------------------------------------

const hemi = new THREE.HemisphereLight(0xe6edf2, 0x8c8478, 1);
// A soft, shadowless headlight (from over the viewer's left shoulder) so walls
// facing different ways read differently in ambient mode.
const fill = new THREE.DirectionalLight(0xffffff, 1);
const sun = new THREE.DirectionalLight(0xfff1dc, 1);
sun.castShadow = true;
sun.shadow.mapSize.set(4096, 4096);
sun.shadow.bias = -0.0002;
sun.shadow.normalBias = 0.03;
scene.add(hemi, fill, fill.target, sun, sun.target);

const ui = {
  mode: store.get("mode", "both"),
  ambient: store.get("ambient", null),
  sun: store.get("sun", null),
  azimuth: 0,
  elevation: 45,
  edges: store.get("edges", true),
};
let bounds = { center: new THREE.Vector3(), radius: 10 };

function applyLighting() {
  const amb = ui.mode === "sun" ? 0.08 : ui.ambient;
  hemi.intensity = amb;
  fill.intensity = amb * 0.5;
  sun.visible = ui.mode !== "ambient";
  sun.intensity = ui.sun;

  // Direction the light travels, from azimuth/elevation (z-up, azimuth from +x toward +y).
  const az = THREE.MathUtils.degToRad(ui.azimuth), el = THREE.MathUtils.degToRad(ui.elevation);
  const toSun = toThree([Math.cos(el) * Math.cos(az), Math.cos(el) * Math.sin(az), Math.sin(el)]);
  const { center, radius } = bounds;
  sun.target.position.copy(center);
  sun.position.copy(center).addScaledVector(toSun, radius * 2);
  const cam = sun.shadow.camera;
  cam.left = cam.bottom = -radius;
  cam.right = cam.top = radius;
  cam.near = radius * 0.1;
  cam.far = radius * 4;
  cam.updateProjectionMatrix();

  for (const k of ["ambient", "sun", "azimuth", "elevation"]) {
    if (ui[k] === null) continue;
    $(k).value = ui[k];
    $(k + "V").textContent = Number(ui[k]).toFixed(k === "azimuth" || k === "elevation" ? 0 : 2);
  }
  for (const b of $("mode").children) b.classList.toggle("on", b.dataset.mode === ui.mode);
  $("edges").checked = ui.edges;
  for (const e of edgeLines) e.visible = ui.edges;
}

$("mode").addEventListener("click", (e) => {
  if (!e.target.dataset.mode) return;
  ui.mode = e.target.dataset.mode;
  store.set("mode", ui.mode);
  applyLighting();
});
for (const k of ["ambient", "sun", "azimuth", "elevation"]) {
  $(k).addEventListener("input", () => {
    ui[k] = parseFloat($(k).value);
    store.set(k, ui[k]);
    applyLighting();
  });
}
$("edges").addEventListener("change", () => { ui.edges = $("edges").checked; store.set("edges", ui.edges); applyLighting(); });

// --- meshes --------------------------------------------------------------------

const concrete = new THREE.MeshStandardMaterial({
  color: 0xb8b3aa, roughness: 0.95, metalness: 0, shadowSide: THREE.DoubleSide,
  polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1, // let outlines win
});
// Faces seen from behind mean the camera is inside solid: paint them plum. (Dark,
// because antialiasing blends a little back-face colour into every silhouette.)
const inside = new THREE.MeshBasicMaterial({
  color: 0x4a1238, side: THREE.BackSide, polygonOffset: true, polygonOffsetFactor: 4, polygonOffsetUnits: 4,
});
const edgeMat = new THREE.LineBasicMaterial({ color: 0x2a2826, transparent: true, opacity: 0.45 });
const sceneObjects = [];
const edgeLines = [];

function loadMeshes(data) {
  for (const o of sceneObjects) { scene.remove(o); o.geometry.dispose(); }
  sceneObjects.length = edgeLines.length = 0;
  for (const m of data.meshes) {
    const src = m.positions;
    const pos = new Float32Array(src.length);
    for (let i = 0; i < src.length; i += 3) {
      pos[i] = src[i]; pos[i + 1] = src[i + 2]; pos[i + 2] = -src[i + 1];
    }
    const geom = new THREE.BufferGeometry();
    geom.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    geom.computeVertexNormals(); // non-indexed: flat per-face normals
    const front = new THREE.Mesh(geom, concrete);
    front.castShadow = front.receiveShadow = true;
    const back = new THREE.Mesh(geom, inside);
    const lineSrc = m.lines;
    const linePos = new Float32Array(lineSrc.length);
    for (let i = 0; i < lineSrc.length; i += 3) {
      linePos[i] = lineSrc[i]; linePos[i + 1] = lineSrc[i + 2]; linePos[i + 2] = -lineSrc[i + 1];
    }
    const lineGeom = new THREE.BufferGeometry();
    lineGeom.setAttribute("position", new THREE.BufferAttribute(linePos, 3));
    const edges = new THREE.LineSegments(lineGeom, edgeMat);
    edgeLines.push(edges);
    sceneObjects.push(front, back, edges);
    scene.add(front, back, edges);
  }
  const [lo, hi] = data.bounds;
  const box = new THREE.Box3().setFromPoints([toThree(lo), toThree(hi)]);
  bounds = { center: box.getCenter(new THREE.Vector3()), radius: Math.max(1, box.getSize(new THREE.Vector3()).length() / 2) };
}

// --- fly controls -----------------------------------------------------------------

const keys = new Set();
let yaw = 0, pitch = 0, speed = store.get("speed", 4);
let spawn = null;

function look(at, target) {
  camera.position.copy(toThree(at));
  if (target) {
    const d = toThree(target).sub(camera.position);
    yaw = Math.atan2(-d.x, -d.z);
    pitch = Math.atan2(d.y, Math.hypot(d.x, d.z));
  }
}

function respawn() {
  if (spawn?.at) look(spawn.at, spawn.look);
  else { camera.position.copy(bounds.center); yaw = pitch = 0; }
}

renderer.domElement.addEventListener("click", () => renderer.domElement.requestPointerLock());
document.addEventListener("pointerlockchange", () => {
  $("cross").style.display = document.pointerLockElement ? "block" : "none";
});
document.addEventListener("mousemove", (e) => {
  if (document.pointerLockElement !== renderer.domElement) return;
  yaw -= e.movementX * 0.0022;
  pitch = Math.max(-1.55, Math.min(1.55, pitch - e.movementY * 0.0022));
});
window.addEventListener("wheel", (e) => {
  speed = Math.max(0.25, Math.min(200, speed * (e.deltaY < 0 ? 1.15 : 1 / 1.15)));
  store.set("speed", speed);
});
window.addEventListener("keydown", (e) => {
  if (e.target.tagName === "INPUT") return;
  keys.add(e.code);
  if (e.code === "KeyR") respawn();
  if (e.code === "Space") e.preventDefault();
});
window.addEventListener("keyup", (e) => keys.delete(e.code));
window.addEventListener("blur", () => keys.clear());

function move(dt) {
  const fwd = new THREE.Vector3(-Math.sin(yaw), 0, -Math.cos(yaw));
  const right = new THREE.Vector3(Math.cos(yaw), 0, -Math.sin(yaw));
  const v = new THREE.Vector3();
  if (keys.has("KeyW")) v.add(fwd);
  if (keys.has("KeyS")) v.sub(fwd);
  if (keys.has("KeyD")) v.add(right);
  if (keys.has("KeyA")) v.sub(right);
  if (keys.has("Space") || keys.has("KeyE")) v.y += 1;
  if (keys.has("KeyC") || keys.has("KeyQ")) v.y -= 1;
  if (v.lengthSq() > 0) {
    const s = speed * (keys.has("ShiftLeft") || keys.has("ShiftRight") ? 4 : 1);
    camera.position.addScaledVector(v.normalize(), s * dt);
  }
  camera.rotation.set(pitch, yaw, 0);
  fill.position.set(-0.6, 0.8, 0.4).applyQuaternion(camera.quaternion).add(camera.position);
  fill.target.position.copy(camera.position);
}

// --- scene updates from the server -----------------------------------------------------

let sceneName = null;
let lastSceneSun = null;

function setStatus(status) {
  $("status").className = status;
  $("status").textContent = status;
}

function sunFromDirection(dir) {
  // `dir` is the direction light travels; the sun sits opposite.
  const [x, y, z] = dir.map((v) => -v);
  ui.azimuth = Math.round((THREE.MathUtils.radToDeg(Math.atan2(y, x)) + 360) % 360);
  ui.elevation = Math.max(1, Math.round(THREE.MathUtils.radToDeg(Math.atan2(z, Math.hypot(x, y)))));
}

async function refresh() {
  const data = await (await fetch("/scene")).json();
  if (!data.name) return;
  $("name").textContent = data.name;
  if (data.error) {
    setStatus("error");
    $("error").textContent = data.error;
    $("error").style.display = "block";
    return;
  }
  $("error").style.display = "none";
  setStatus("ready");
  loadMeshes(data);
  spawn = data.spawn;

  // Scene-supplied light settings apply unless the user has moved the sliders.
  if (ui.ambient === null) ui.ambient = data.ambient.intensity;
  if (ui.sun === null) ui.sun = data.sun.intensity;
  const sunKey = JSON.stringify(data.sun.direction);
  if (sunKey !== lastSceneSun) { sunFromDirection(data.sun.direction); lastSceneSun = sunKey; }
  applyLighting();

  const s = data.stats;
  $("stats").textContent = `${s.triangles} tris · ${s.polygons} polys · ${s.build_ms} ms`;

  if (sceneName !== data.name) {
    sceneName = data.name;
    const saved = store.get("camera:" + sceneName, null);
    if (saved) { camera.position.fromArray(saved.p); yaw = saved.yaw; pitch = saved.pitch; }
    else respawn();
  }
}

function connect() {
  const events = new EventSource("/events");
  events.onmessage = (e) => {
    const { status } = JSON.parse(e.data);
    if (status === "building") setStatus("building");
    else refresh();
  };
  events.onerror = () => setStatus("building");
}
applyLighting();
connect();

// --- main loop ---------------------------------------------------------------------------

const clock = new THREE.Clock();
let saveTimer = 0;
renderer.setAnimationLoop(() => {
  const dt = Math.min(clock.getDelta(), 0.1);
  move(dt);
  saveTimer += dt;
  if (saveTimer > 0.5 && sceneName) {
    saveTimer = 0;
    store.set("camera:" + sceneName, { p: camera.position.toArray(), yaw, pitch });
    const [x, y, z] = fromThree(camera.position);
    $("pos").textContent = `x ${x.toFixed(2)}  y ${y.toFixed(2)}  z ${z.toFixed(2)} · ${speed.toFixed(1)} m/s`;
  }
  renderer.render(scene, camera);
});
