// =========================================================
// VECTOR
// Lógica de la interfaz y del visor
// =========================================================


// =========================================================
// ESTADO GLOBAL
// =========================================================

const state = {

    // Manifest del .imgmap actualmente abierto
    manifest: null,

    // Ruta del .imgmap actualmente abierto
    path: null,

    // Rama actualmente abierta
    branchIndex: null,

    // Zoom GLOBAL de VECTOR (no pertenece a una rama ni a un archivo)
    zoom: 40,

    // Información del último archivo
    lastFile: null,

    // Biblioteca
    library: [],

    // Velocidad de desplazamiento con las flechas arriba/abajo (px por segundo)
    scrollSpeed: 1200,
    scrollSpeedDefault: 1200
};


// =========================================================
// CONFIGURACIÓN DEL ZOOM
// =========================================================

const ZOOM_MIN = 10;
const ZOOM_MAX = 150;
const ZOOM_STEP = 5;
const ZOOM_DEFAULT = 40;

const SPEED_MIN = 100;
const SPEED_MAX = 5000;


// =========================================================
// ELEMENTOS HTML
// =========================================================

const homeView = document.getElementById("home-view");
const rootView = document.getElementById("root-view");
const branchView = document.getElementById("branch-view");

const rootTitle = document.getElementById("root-title");
const cardsEl = document.getElementById("cards");

const branchTitleEl = document.getElementById("branch-title");
const stripEl = document.getElementById("strip");

const zoomInput = document.getElementById("zoom-input");

const libraryList = document.getElementById("library-list");
const libraryEmpty = document.getElementById("library-empty");
const libraryLocation = document.getElementById("library-location");

const continueButton = document.getElementById("btn-continue");
const createButton = document.getElementById("btn-create");
const libraryFolderButton = document.getElementById("btn-library-folder");
const continueFile = document.getElementById("continue-file");

const speedInput = document.getElementById("speed-input");
const speedApply = document.getElementById("speed-apply");
const speedReset = document.getElementById("speed-reset");
const speedHint = document.getElementById("speed-hint");


// =========================================================
// UTILIDADES
// =========================================================

function hasPyWebView() {

    return Boolean(
        window.pywebview &&
        window.pywebview.api
    );
}


function apiExists(name) {

    return (
        hasPyWebView() &&
        typeof window.pywebview.api[name] === "function"
    );
}


// =========================================================
// VISIBILIDAD DE VISTAS
// =========================================================

function leaveFocus() {

    // Evita que un campo oculto siga "escribiendo" y bloquee las flechas.
    if (document.activeElement && document.activeElement.blur) {

        document.activeElement.blur();
    }
}


function showHome() {

    leaveFocus();
    stopKeyScroll();

    homeView.classList.remove("hidden");
    rootView.classList.add("hidden");
    branchView.classList.add("hidden");

    state.branchIndex = null;
}


function showRoot() {

    leaveFocus();
    stopKeyScroll();

    homeView.classList.add("hidden");
    rootView.classList.remove("hidden");
    branchView.classList.add("hidden");

    state.branchIndex = null;

    rootView.scrollTop = 0;
}


function showBranch() {

    leaveFocus();

    homeView.classList.add("hidden");
    rootView.classList.add("hidden");
    branchView.classList.remove("hidden");
}


// =========================================================
// URL DE UNA IMAGEN DEL IMGMap
// =========================================================

function imgUrl(arcname) {

    return "/img/" + encodeURIComponent(arcname);
}


// =========================================================
// ZOOM GLOBAL
// =========================================================

function applyZoom(value) {

    value = Number(value);

    if (!Number.isFinite(value)) {

        value = ZOOM_DEFAULT;
    }

    value = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, value));

    // Ajustamos al múltiplo de 5 más cercano
    value = Math.round(value / ZOOM_STEP) * ZOOM_STEP;

    value = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, value));

    state.zoom = value;

    zoomInput.value = value;

    stripEl.style.setProperty("--zoom-vw", value + "vw");
}


// =========================================================
// MANIFEST
// =========================================================

async function fetchManifest() {

    try {

        const response = await fetch("/manifest", { cache: "no-store" });

        if (!response.ok) {

            return null;
        }

        return await response.json();

    } catch (error) {

        console.error("No se pudo obtener el manifest:", error);

        return null;
    }
}


// =========================================================
// ÍNDICE DEL MAPA
// =========================================================

function renderRoot() {

    const manifest = state.manifest;

    if (!manifest) {

        return;
    }

    // La portada raíz NO se muestra en esta pantalla.

    rootTitle.textContent = manifest.title || "Mapa";

    cardsEl.innerHTML = "";

    const branches = Array.isArray(manifest.branches) ? manifest.branches : [];

    branches.forEach((branch, index) => {

        const card = document.createElement("article");
        card.className = "card";

        const image = document.createElement("img");
        image.src = imgUrl(branch.cover);
        image.loading = "lazy";
        image.alt = branch.name || "Rama";

        const name = document.createElement("div");
        name.className = "card-name";
        name.textContent = branch.name || "Rama";

        card.appendChild(image);
        card.appendChild(name);

        card.addEventListener("click", () => openBranch(index));

        cardsEl.appendChild(card);
    });
}


// =========================================================
// ABRIR RAMA
// =========================================================

function openBranch(index) {

    const manifest = state.manifest;

    if (!manifest) {

        return;
    }

    const branches = Array.isArray(manifest.branches) ? manifest.branches : [];

    // Antes de la primera o después de la última: no hacemos nada.
    if (index < 0 || index >= branches.length) {

        return;
    }

    state.branchIndex = index;

    const branch = branches[index];

    branchTitleEl.textContent = branch.name || "Rama";

    stripEl.innerHTML = "";

    const images = Array.isArray(branch.images) ? branch.images : [];

    // branch.images NO incluye la portada de la rama.

    images.forEach((arcname, imageIndex) => {

        const image = document.createElement("img");

        image.src = imgUrl(arcname);
        image.alt = `${branch.name || "Rama"} - imagen ${imageIndex + 1}`;
        image.loading = "lazy";
        image.decoding = "async";

        stripEl.appendChild(image);
    });

    // El zoom GLOBAL se conserva al cambiar de rama.
    applyZoom(state.zoom);

    showBranch();

    stripEl.scrollTop = 0;
}


// =========================================================
// VOLVER
// =========================================================

function goBack() {

    if (state.manifest && state.branchIndex !== null) {

        showRoot();

        return;
    }

    // Desde el índice, ESC vuelve a la pantalla inicial.
    if (state.manifest) {

        state.manifest = null;
        state.path = null;

        showHome();

        // Refrescamos la biblioteca y el texto de CONTINUAR
        // (por si se creó o se abrió un archivo nuevo).
        loadLibrary();
        loadLastFileInfo();
    }
}


// =========================================================
// CAMBIAR ENTRE RAMAS
// =========================================================

function goSibling(delta) {

    if (state.branchIndex === null) {

        return;
    }

    // openBranch() comprueba si la rama existe.
    openBranch(state.branchIndex + delta);
}


// =========================================================
// ABRIR UN IMGMap
// =========================================================

async function openFromPath(path) {

    if (!path) {

        return false;
    }

    state.path = path;

    const manifest = await fetchManifest();

    if (!manifest) {

        console.error("No se pudo cargar el manifest.");

        return false;
    }

    state.manifest = manifest;

    applyZoom(state.zoom);

    renderRoot();

    showRoot();

    return true;
}


// Procesa la respuesta de Python: {path}, {error} o null (cancelado).
async function handleOpenResult(result) {

    if (!result) {

        return;
    }

    if (result.error) {

        alert(result.error);

        return;
    }

    if (result.path) {

        await openFromPath(result.path);
    }
}


// =========================================================
// ABRIR ARCHIVO CON EL SELECTOR
// =========================================================

async function chooseAndOpen() {

    if (!apiExists("choose_and_open")) {

        console.warn("choose_and_open todavía no está disponible.");

        return;
    }

    await handleOpenResult(await window.pywebview.api.choose_and_open());
}


// =========================================================
// CONTINUAR
// =========================================================

async function continueLastFile() {

    if (!apiExists("open_last_file")) {

        return;
    }

    try {

        await handleOpenResult(await window.pywebview.api.open_last_file());

    } catch (error) {

        console.error("Error al continuar:", error);
    }
}


// =========================================================
// CREAR
// =========================================================

async function createNewMap() {

    if (!apiExists("create_new_map")) {

        console.info("create_new_map no está disponible.");

        return;
    }

    try {

        // Python pide la carpeta y dónde guardar, crea el .imgmap y lo abre.
        await handleOpenResult(await window.pywebview.api.create_new_map());

    } catch (error) {

        console.error("Error al crear el .imgmap:", error);
    }
}


// =========================================================
// BIBLIOTECA
// =========================================================

function clearLibrary() {

    libraryList.innerHTML = "";

    libraryList.appendChild(libraryEmpty);
}


function renderLibrary(files) {

    state.library = Array.isArray(files) ? files : [];

    clearLibrary();

    if (state.library.length === 0) {

        libraryEmpty.classList.remove("hidden");

        return;
    }

    libraryEmpty.classList.add("hidden");

    state.library.forEach((file) => {

        const card = document.createElement("article");
        card.className = "library-card";

        const imageContainer = document.createElement("div");
        imageContainer.className = "library-card-image-container";

        const image = document.createElement("img");
        image.className = "library-card-image";

        if (file.coverUrl) {

            image.src = file.coverUrl;

        } else if (file.cover) {

            image.src = imgUrl(file.cover);
        }

        image.alt = file.name || ".imgmap";
        image.loading = "lazy";

        imageContainer.appendChild(image);

        const name = document.createElement("div");
        name.className = "library-card-name";
        name.textContent = file.name || ".imgmap";

        card.appendChild(imageContainer);
        card.appendChild(name);

        card.addEventListener("click", () => openLibraryFile(file));

        libraryList.appendChild(card);
    });
}


// =========================================================
// ABRIR DESDE BIBLIOTECA
// =========================================================

async function openLibraryFile(file) {

    if (!file || !file.path) {

        return;
    }

    if (!apiExists("open_library_file")) {

        console.error("open_library_file no está disponible.");

        return;
    }

    try {

        await handleOpenResult(
            await window.pywebview.api.open_library_file(file.path)
        );

    } catch (error) {

        console.error("Error al abrir el archivo de biblioteca:", error);
    }
}


// =========================================================
// CARGAR BIBLIOTECA
// =========================================================

async function loadLibrary() {

    if (!apiExists("get_library")) {

        libraryLocation.textContent = "Biblioteca no disponible todavía";

        renderLibrary([]);

        return;
    }

    try {

        const result = await window.pywebview.api.get_library();

        if (!result) {

            renderLibrary([]);

            return;
        }

        libraryLocation.textContent =
            result.path || "Biblioteca no seleccionada";

        renderLibrary(result.files || []);

    } catch (error) {

        console.error("Error al cargar la biblioteca:", error);

        renderLibrary([]);
    }
}


// =========================================================
// ELEGIR CARPETA DE BIBLIOTECA
// =========================================================

async function chooseLibraryFolder() {

    if (!apiExists("choose_library_folder")) {

        console.info("choose_library_folder todavía no está disponible.");

        return;
    }

    try {

        const result = await window.pywebview.api.choose_library_folder();

        if (!result) {

            return;
        }

        if (result.error) {

            alert(result.error);

            return;
        }

        if (result.path) {

            libraryLocation.textContent = result.path;
        }

        renderLibrary(result.files || []);

    } catch (error) {

        console.error("Error al seleccionar la biblioteca:", error);
    }
}


// =========================================================
// ACTUALIZAR TEXTO DE CONTINUAR
// =========================================================

async function loadLastFileInfo() {

    if (!apiExists("get_last_file")) {

        continueFile.textContent = "No hay información del último archivo";

        continueButton.disabled = true;

        return;
    }

    try {

        const result = await window.pywebview.api.get_last_file();

        if (result && result.path) {

            state.lastFile = result;

            continueFile.textContent = result.name || result.path;

            continueButton.disabled = false;

        } else {

            continueFile.textContent = "No hay un archivo reciente";

            continueButton.disabled = true;
        }

    } catch (error) {

        console.error("Error obteniendo el último archivo:", error);

        continueButton.disabled = true;
    }
}


// =========================================================
// VELOCIDAD DE DESPLAZAMIENTO
// =========================================================

function clampSpeed(value) {

    value = Number(value);

    if (!Number.isFinite(value)) {

        return null;
    }

    return Math.max(SPEED_MIN, Math.min(SPEED_MAX, Math.round(value)));
}


// Habilita / deshabilita APLICAR y RESTABLECER según lo que hay escrito.
function refreshSpeedUi() {

    const typed = clampSpeed(speedInput.value);

    speedApply.disabled =
        typed === null ||
        typed === state.scrollSpeed;

    speedReset.disabled =
        state.scrollSpeed === state.scrollSpeedDefault &&
        typed === state.scrollSpeedDefault;
}


function setSpeedFromApi(info) {

    if (!info || !info.value) {

        return;
    }

    state.scrollSpeed = info.value;

    if (info.default) {

        state.scrollSpeedDefault = info.default;
    }

    speedInput.value = state.scrollSpeed;

    speedHint.textContent =
        "Flechas ↑ ↓ · px por segundo · por defecto " +
        state.scrollSpeedDefault;

    refreshSpeedUi();
}


async function loadScrollSpeed() {

    if (!apiExists("get_scroll_speed")) {

        refreshSpeedUi();

        return;
    }

    try {

        setSpeedFromApi(await window.pywebview.api.get_scroll_speed());

    } catch (error) {

        console.error("Error obteniendo la velocidad:", error);
    }
}


async function applySpeed() {

    const typed = clampSpeed(speedInput.value);

    if (typed === null) {

        speedInput.value = state.scrollSpeed;

        refreshSpeedUi();

        return;
    }

    if (apiExists("set_scroll_speed")) {

        try {

            const info = await window.pywebview.api.set_scroll_speed(typed);

            if (info && info.value) {

                setSpeedFromApi(info);

                return;
            }

        } catch (error) {

            console.error("Error guardando la velocidad:", error);
        }
    }

    // Sin backend: al menos se usa durante esta sesión.
    state.scrollSpeed = typed;

    speedInput.value = typed;

    refreshSpeedUi();
}


async function resetSpeed() {

    if (apiExists("reset_scroll_speed")) {

        try {

            const info = await window.pywebview.api.reset_scroll_speed();

            if (info && info.value) {

                setSpeedFromApi(info);

                return;
            }

        } catch (error) {

            console.error("Error restableciendo la velocidad:", error);
        }
    }

    state.scrollSpeed = state.scrollSpeedDefault;

    speedInput.value = state.scrollSpeed;

    refreshSpeedUi();
}


speedInput.addEventListener("input", refreshSpeedUi);

speedInput.addEventListener("keydown", (event) => {

    if (event.key === "Enter") {

        event.preventDefault();

        applySpeed();
    }
});

speedApply.addEventListener("click", applySpeed);

speedReset.addEventListener("click", resetSpeed);


// =========================================================
// DESPLAZAMIENTO CON FLECHAS ARRIBA / ABAJO
// =========================================================

/*
 * Antes cada pulsación (y cada repetición de la tecla) lanzaba un
 * scrollBy({behavior: "smooth"}). Esas animaciones se pisaban unas a
 * otras y el movimiento se trababa.
 *
 * Ahora, mientras la flecha está apretada, un bucle con
 * requestAnimationFrame mueve el scroll a una velocidad constante
 * (state.scrollSpeed en píxeles por segundo), igual de fluido que
 * la rueda del mouse.
 */

const scrollKeys = { up: false, down: false };

let scrollFrameId = null;
let lastFrameTime = 0;
let scrollRemainder = 0;


function scrollFrame(now) {

    const direction =
        (scrollKeys.down ? 1 : 0) -
        (scrollKeys.up ? 1 : 0);

    if (direction === 0 || state.branchIndex === null) {

        stopKeyScroll();

        return;
    }

    // Máximo 50 ms por cuadro para evitar saltos si la ventana se congela.
    const elapsed = Math.min(now - lastFrameTime, 50);

    lastFrameTime = now;

    const delta =
        direction * state.scrollSpeed * elapsed / 1000 +
        scrollRemainder;

    const whole = Math.trunc(delta);

    scrollRemainder = delta - whole;

    if (whole !== 0) {

        stripEl.scrollTop += whole;
    }

    scrollFrameId = requestAnimationFrame(scrollFrame);
}


function startKeyScroll() {

    if (scrollFrameId !== null) {

        return;
    }

    lastFrameTime = performance.now();

    scrollRemainder = 0;

    scrollFrameId = requestAnimationFrame(scrollFrame);
}


function stopKeyScroll() {

    scrollKeys.up = false;
    scrollKeys.down = false;

    if (scrollFrameId !== null) {

        cancelAnimationFrame(scrollFrameId);

        scrollFrameId = null;
    }

    scrollRemainder = 0;
}


// =========================================================
// EVENTOS - INICIO
// =========================================================

continueButton.addEventListener("click", continueLastFile);

createButton.addEventListener("click", createNewMap);

libraryFolderButton.addEventListener("click", chooseLibraryFolder);


// =========================================================
// EVENTOS - ZOOM
// =========================================================

document.getElementById("zoom-in")
    .addEventListener("click", () => applyZoom(state.zoom + ZOOM_STEP));

document.getElementById("zoom-out")
    .addEventListener("click", () => applyZoom(state.zoom - ZOOM_STEP));

zoomInput.addEventListener("change", () => applyZoom(zoomInput.value));


// =========================================================
// TECLADO
// =========================================================

document.addEventListener("keydown", (event) => {

    const activeElement = document.activeElement;

    const tag = activeElement ? activeElement.tagName : "";

    // No capturamos las teclas mientras se escribe en el campo del zoom.
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") {

        return;
    }

    // ESC
    if (event.key === "Escape") {

        event.preventDefault();

        goBack();

        return;
    }

    // IZQUIERDA
    if (event.key === "ArrowLeft") {

        if (state.branchIndex !== null) {

            event.preventDefault();

            goSibling(-1);
        }

        return;
    }

    // DERECHA
    if (event.key === "ArrowRight") {

        if (state.branchIndex !== null) {

            event.preventDefault();

            goSibling(1);
        }

        return;
    }

    // ARRIBA
    if (event.key === "ArrowUp") {

        if (state.branchIndex !== null) {

            event.preventDefault();

            scrollKeys.up = true;

            startKeyScroll();
        }

        return;
    }

    // ABAJO
    if (event.key === "ArrowDown") {

        if (state.branchIndex !== null) {

            event.preventDefault();

            scrollKeys.down = true;

            startKeyScroll();
        }

        return;
    }
});


document.addEventListener("keyup", (event) => {

    if (event.key === "ArrowUp") {

        scrollKeys.up = false;
    }

    if (event.key === "ArrowDown") {

        scrollKeys.down = false;
    }

    if (!scrollKeys.up && !scrollKeys.down) {

        stopKeyScroll();
    }
});

// Si la ventana pierde el foco con una flecha apretada, se detiene.
window.addEventListener("blur", stopKeyScroll);


// =========================================================
// RUEDA DEL MOUSE
// =========================================================

// No se intercepta: el navegador maneja el scroll directamente.


// =========================================================
// INICIO DE LA APLICACIÓN
// =========================================================

async function initialize() {

    applyZoom(ZOOM_DEFAULT);

    showHome();

    await loadLibrary();

    await loadLastFileInfo();

    await loadScrollSpeed();

    // Si Python arrancó con un archivo ya abierto, lo cargamos.
    const manifest = await fetchManifest();

    if (manifest && manifest._path) {

        await openFromPath(manifest._path);
    }
}


/*
 * Arranque seguro.
 *
 * Antes solo se escuchaba el evento "pywebviewready". Si ese evento ya
 * había ocurrido cuando se ejecutaba este archivo, initialize() nunca
 * corría y la pantalla quedaba sin biblioteca ni CONTINUAR (fallaba
 * "a veces"). Ahora se cubren los tres casos y se ejecuta UNA sola vez.
 */

let started = false;

function start() {

    if (started) {

        return;
    }

    started = true;

    initialize();
}

window.addEventListener("pywebviewready", start);

if (hasPyWebView()) {

    start();

} else {

    const poll = setInterval(() => {

        if (hasPyWebView()) {

            clearInterval(poll);

            start();
        }

    }, 100);
}
