// app.js - logica del lector de mapas de imagenes

const state = {
  manifest: null,
  path: null,
  branchIndex: null,
  zoom: 50,
};

const ZOOM_MIN = 10, ZOOM_MAX = 150, ZOOM_STEP = 5, ZOOM_DEFAULT = 50;

const rootView = document.getElementById("root-view");
const branchView = document.getElementById("branch-view");
const rootCover = document.getElementById("root-cover");
const rootTitle = document.getElementById("root-title");
const cardsEl = document.getElementById("cards");
const stripEl = document.getElementById("strip");
const branchTitleEl = document.getElementById("branch-title");
const zoomInput = document.getElementById("zoom-input");

function imgUrl(arcname) {
  return "/img/" + encodeURIComponent(arcname);
}

function zoomKey(path) {
  return "imgmap_zoom:" + path;
}

function loadZoomForPath(path) {
  const saved = localStorage.getItem(zoomKey(path));
  return saved ? parseInt(saved, 10) : ZOOM_DEFAULT;
}

function saveZoomForPath(path, value) {
  localStorage.setItem(zoomKey(path), String(value));
}

function applyZoom(value) {
  value = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, value));
  state.zoom = value;
  zoomInput.value = value;
  stripEl.style.setProperty("--zoom-vw", value + "vw");
  if (state.path) saveZoomForPath(state.path, value);
}

async function fetchManifest() {
  const res = await fetch("/manifest");
  if (!res.ok) return null;
  return res.json();
}

function renderRoot() {
  const m = state.manifest;
  rootCover.src = imgUrl(m.cover);
  rootTitle.textContent = m.title || "";
  cardsEl.innerHTML = "";
  m.branches.forEach((branch, index) => {
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <img src="${imgUrl(branch.cover)}" loading="lazy" alt="${branch.name}" />
      <div class="card-name">${branch.name}</div>
    `;
    card.addEventListener("click", () => openBranch(index));
    cardsEl.appendChild(card);
  });
}

function openBranch(index) {
  const m = state.manifest;
  if (index < 0 || index >= m.branches.length) return;
  state.branchIndex = index;
  const branch = m.branches[index];

  branchTitleEl.textContent = branch.name;
  stripEl.innerHTML = "";
  branch.images.forEach((arcname) => {
    const img = document.createElement("img");
    img.src = imgUrl(arcname);
    img.loading = "lazy"; // el navegador prioriza solas las que estan cerca de lo visible
    img.alt = arcname;
    stripEl.appendChild(img);
  });

  applyZoom(state.zoom);
  rootView.classList.add("hidden");
  branchView.classList.remove("hidden");
  window.scrollTo(0, 0);
}

function goBack() {
  if (state.branchIndex === null) return;
  state.branchIndex = null;
  branchView.classList.add("hidden");
  rootView.classList.remove("hidden");
}

function goSibling(delta) {
  if (state.branchIndex === null) return;
  openBranch(state.branchIndex + delta);
}

async function openFromPath(path) {
  state.path = path;
  state.manifest = await fetchManifest();
  if (!state.manifest) return;
  state.zoom = loadZoomForPath(path);
  renderRoot();
  goBack(); // asegura que arranque en la vista raiz
}

document.getElementById("btn-open").addEventListener("click", async () => {
  const result = await window.pywebview.api.choose_and_open();
  if (result && result.path) {
    await openFromPath(result.path);
  }
});

document.getElementById("zoom-in").addEventListener("click", () => applyZoom(state.zoom + ZOOM_STEP));
document.getElementById("zoom-out").addEventListener("click", () => applyZoom(state.zoom - ZOOM_STEP));
zoomInput.addEventListener("change", () => applyZoom(parseInt(zoomInput.value, 10) || ZOOM_DEFAULT));

document.addEventListener("keydown", (event) => {
  const tag = document.activeElement.tagName;
  if (tag === "INPUT") return; // no interferir mientras se escribe un numero

  if (event.key === "Escape") goBack();
  else if (event.key === "ArrowRight") goSibling(1);
  else if (event.key === "ArrowLeft") goSibling(-1);
});

// Al cargar la pagina: si Python ya abrio un archivo (por linea de comandos),
// el /manifest responde de una, y lo mostramos directo.
window.addEventListener("DOMContentLoaded", async () => {
  const manifest = await fetchManifest();
  if (manifest && manifest._path) {
    await openFromPath(manifest._path);
  }
});
