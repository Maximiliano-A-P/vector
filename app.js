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

    // Zoom GLOBAL de VECTOR
    //
    // Este valor NO pertenece a una rama.
    // Tampoco pertenece a un archivo.
    //
    // Si pasa de 40 a 45:
    //
    // rama 1 -> 45
    // rama 2 -> 45
    // rama 3 -> 45
    //
    zoom: 40,

    // Información del último archivo
    lastFile: null,

    // Biblioteca
    library: []
};


// =========================================================
// CONFIGURACIÓN DEL ZOOM
// =========================================================

const ZOOM_MIN = 10;
const ZOOM_MAX = 150;
const ZOOM_STEP = 5;
const ZOOM_DEFAULT = 40;


// =========================================================
// ELEMENTOS HTML
// =========================================================

const homeView =
    document.getElementById("home-view");

const rootView =
    document.getElementById("root-view");

const branchView =
    document.getElementById("branch-view");


const rootTitle =
    document.getElementById("root-title");

const cardsEl =
    document.getElementById("cards");


const branchTitleEl =
    document.getElementById("branch-title");

const stripEl =
    document.getElementById("strip");


const zoomInput =
    document.getElementById("zoom-input");


const libraryList =
    document.getElementById("library-list");

const libraryEmpty =
    document.getElementById("library-empty");

const libraryLocation =
    document.getElementById("library-location");


const continueButton =
    document.getElementById("btn-continue");

const createButton =
    document.getElementById("btn-create");

const libraryFolderButton =
    document.getElementById("btn-library-folder");

const continueFile =
    document.getElementById("continue-file");


// =========================================================
// UTILIDADES
// =========================================================

function hasPyWebView() {

    return (
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
// PANTALLA COMPLETA
// =========================================================

async function requestFullscreen() {

    /*
     * Los navegadores no permiten iniciar fullscreen
     * automáticamente sin una interacción del usuario.
     *
     * Por eso lo solicitamos cuando el usuario pulsa
     * una acción de VECTOR.
     */

    if (
        document.fullscreenElement ||
        !document.documentElement.requestFullscreen
    ) {
        return;
    }

    try {

        await document.documentElement.requestFullscreen();

    } catch (error) {

        /*
         * En el .exe definitivo el runtime podrá abrir
         * directamente la ventana en fullscreen.
         *
         * No hacemos fallar VECTOR si el navegador/runtime
         * no permite fullscreen.
         */

        console.debug(
            "Fullscreen no disponible:",
            error
        );
    }
}


// =========================================================
// VISIBILIDAD DE VISTAS
// =========================================================

function showHome() {

    homeView.classList.remove("hidden");

    rootView.classList.add("hidden");

    branchView.classList.add("hidden");

    state.branchIndex = null;
}


function showRoot() {

    homeView.classList.add("hidden");

    rootView.classList.remove("hidden");

    branchView.classList.add("hidden");

    state.branchIndex = null;

    rootView.scrollTop = 0;
}


function showBranch() {

    homeView.classList.add("hidden");

    rootView.classList.add("hidden");

    branchView.classList.remove("hidden");
}


// =========================================================
// URL DE UNA IMAGEN DEL IMGMap
// =========================================================

function imgUrl(arcname) {

    return (
        "/img/" +
        encodeURIComponent(arcname)
    );
}


// =========================================================
// ZOOM GLOBAL
// =========================================================

function applyZoom(value) {

    value = Number(value);

    if (!Number.isFinite(value)) {

        value = ZOOM_DEFAULT;
    }


    value = Math.max(
        ZOOM_MIN,
        Math.min(ZOOM_MAX, value)
    );


    // Ajustamos al múltiplo de 5 más cercano
    value =
        Math.round(value / ZOOM_STEP) *
        ZOOM_STEP;


    value = Math.max(
        ZOOM_MIN,
        Math.min(ZOOM_MAX, value)
    );


    state.zoom = value;

    zoomInput.value = value;


    /*
     * Este es el punto importante:
     *
     * El zoom está aplicado al contenedor de imágenes.
     *
     * No se guarda por archivo.
     * No se guarda por rama.
     */

    stripEl.style.setProperty(
        "--zoom-vw",
        value + "vw"
    );
}


// =========================================================
// MANIFEST
// =========================================================

async function fetchManifest() {

    try {

        const response =
            await fetch("/manifest", {
                cache: "no-store"
            });


        if (!response.ok) {

            return null;
        }


        return await response.json();

    } catch (error) {

        console.error(
            "No se pudo obtener el manifest:",
            error
        );

        return null;
    }
}


// =========================================================
// ÍNDICE DEL MAPA
// =========================================================

function renderRoot() {

    const manifest =
        state.manifest;


    if (!manifest) {

        return;
    }


    /*
     * IMPORTANTE:
     *
     * Ya NO mostramos la portada raíz.
     *
     * La portada raíz sigue existiendo dentro
     * del formato .imgmap, pero no forma parte
     * de esta interfaz.
     */

    rootTitle.textContent =
        manifest.title || "Mapa";


    cardsEl.innerHTML = "";


    const branches =
        Array.isArray(manifest.branches)
            ? manifest.branches
            : [];


    branches.forEach(
        (branch, index) => {

            const card =
                document.createElement("article");


            card.className =
                "card";


            const image =
                document.createElement("img");


            image.src =
                imgUrl(branch.cover);


            image.loading =
                "lazy";


            image.alt =
                branch.name || "Rama";


            const name =
                document.createElement("div");


            name.className =
                "card-name";


            name.textContent =
                branch.name || "Rama";


            card.appendChild(image);

            card.appendChild(name);


            /*
             * Se puede hacer clic tanto sobre
             * la imagen como sobre el nombre,
             * porque todo es una sola tarjeta.
             */

            card.addEventListener(
                "click",
                () => openBranch(index)
            );


            cardsEl.appendChild(card);
        }
    );
}


// =========================================================
// ABRIR RAMA
// =========================================================

function openBranch(index) {

    const manifest =
        state.manifest;


    if (!manifest) {

        return;
    }


    const branches =
        Array.isArray(manifest.branches)
            ? manifest.branches
            : [];


    /*
     * Si intentamos ir antes de la primera
     * o después de la última rama,
     * simplemente no hacemos nada.
     */

    if (
        index < 0 ||
        index >= branches.length
    ) {

        return;
    }


    state.branchIndex =
        index;


    const branch =
        branches[index];


    branchTitleEl.textContent =
        branch.name || "Rama";


    stripEl.innerHTML =
        "";


    const images =
        Array.isArray(branch.images)
            ? branch.images
            : [];


    /*
     * IMPORTANTE:
     *
     * branch.images NO incluye la portada
     * de la rama según el formato actual.
     *
     * Por eso solamente mostramos las imágenes
     * que pertenecen a la tira.
     */

    images.forEach(
        (arcname, imageIndex) => {

            const image =
                document.createElement("img");


            image.src =
                imgUrl(arcname);


            image.alt =
                `${branch.name || "Rama"} - imagen ${imageIndex + 1}`;


            /*
             * Lazy loading.
             *
             * El navegador no tiene que decodificar
             * inmediatamente todas las imágenes.
             */

            image.loading =
                "lazy";


            image.decoding =
                "async";


            stripEl.appendChild(image);
        }
    );


    /*
     * Conservamos el zoom GLOBAL.
     *
     * Al cambiar de rama NO vuelve a 40%.
     */

    applyZoom(state.zoom);


    showBranch();


    /*
     * Comenzamos la rama desde arriba.
     */

    stripEl.scrollTop = 0;
}


// =========================================================
// VOLVER AL ÍNDICE
// =========================================================

function goBack() {

    if (
        state.manifest &&
        state.branchIndex !== null
    ) {

        showRoot();

        return;
    }


    /*
     * Si no estamos dentro de una rama
     * pero tenemos un mapa abierto,
     * ESC vuelve a la pantalla inicial.
     */

    if (state.manifest) {

        state.manifest = null;

        state.path = null;

        showHome();
    }
}


// =========================================================
// CAMBIAR ENTRE RAMAS
// =========================================================

function goSibling(delta) {

    if (
        state.branchIndex === null
    ) {

        return;
    }


    const nextIndex =
        state.branchIndex + delta;


    /*
     * openBranch() se encarga de comprobar
     * si la rama existe.
     */

    openBranch(nextIndex);
}


// =========================================================
// ABRIR UN IMGMap
// =========================================================

async function openFromPath(path) {

    if (!path) {

        return false;
    }


    state.path =
        path;


    const manifest =
        await fetchManifest();


    if (!manifest) {

        console.error(
            "No se pudo cargar el manifest."
        );

        return false;
    }


    state.manifest =
        manifest;


    /*
     * El zoom NO se obtiene de este archivo.
     *
     * Es global.
     */

    applyZoom(state.zoom);


    renderRoot();


    showRoot();


    return true;
}


// =========================================================
// ABRIR ARCHIVO CON EL SELECTOR ACTUAL
// =========================================================

async function chooseAndOpen() {

    if (!apiExists("choose_and_open")) {

        console.warn(
            "choose_and_open todavía no está disponible."
        );

        return;
    }


    const result =
        await window.pywebview.api.choose_and_open();


    if (
        result &&
        result.path
    ) {

        await openFromPath(
            result.path
        );
    }
}


// =========================================================
// CONTINUAR
// =========================================================

async function continueLastFile() {

    await requestFullscreen();

    if (!apiExists("open_last_file")) {

        return;
    }

    try {

        const result =
            await window.pywebview.api.open_last_file();

        if (
            result &&
            result.path
        ) {

            await openFromPath(
                result.path
            );
        }

    } catch (error) {

        console.error(
            "Error al continuar:",
            error
        );
    }
}


// =========================================================
// CREAR
// =========================================================

async function createNewMap() {

    await requestFullscreen();


    /*
     * El creador se conectará en una etapa posterior.
     *
     * Si el backend ya dispone de create_new_map(),
     * lo utilizamos.
     */

    if (apiExists("create_new_map")) {

        try {

            await window.pywebview.api.create_new_map();

        } catch (error) {

            console.error(
                "Error al abrir el creador:",
                error
            );
        }

        return;
    }


    console.info(
        "El creador de .imgmap se conectará en el siguiente paso."
    );
}


// =========================================================
// BIBLIOTECA
// =========================================================

function clearLibrary() {

    libraryList.innerHTML = "";

    libraryList.appendChild(
        libraryEmpty
    );
}


function renderLibrary(files) {

    state.library =
        Array.isArray(files)
            ? files
            : [];


    clearLibrary();


    if (state.library.length === 0) {

        libraryEmpty.classList.remove(
            "hidden"
        );

        return;
    }


    libraryEmpty.classList.add(
        "hidden"
    );


    state.library.forEach(
        (file) => {

            const card =
                document.createElement("article");


            card.className =
                "library-card";


            const imageContainer =
                document.createElement("div");


            imageContainer.className =
                "library-card-image-container";


            const image =
                document.createElement("img");


            image.className =
                "library-card-image";


            /*
             * En el Paso 2 el backend proporcionará
             * la URL de la portada.
             */

            if (file.coverUrl) {

                image.src =
                    file.coverUrl;

            } else if (file.cover) {

                image.src =
                    imgUrl(file.cover);

            }


            image.alt =
                file.name || ".imgmap";


            image.loading =
                "lazy";


            imageContainer.appendChild(
                image
            );


            const name =
                document.createElement("div");


            name.className =
                "library-card-name";


            name.textContent =
                file.name || ".imgmap";


            card.appendChild(
                imageContainer
            );


            card.appendChild(
                name
            );


            card.addEventListener(
                "click",
                () => openLibraryFile(file)
            );


            libraryList.appendChild(
                card
            );
        }
    );
}


// =========================================================
// ABRIR DESDE BIBLIOTECA
// =========================================================

async function openLibraryFile(file) {

    if (!file || !file.path) {

        return;
    }

    await requestFullscreen();

    if (!apiExists("open_library_file")) {

        console.error(
            "open_library_file no está disponible."
        );

        return;
    }

    try {

        const result =
            await window.pywebview.api.open_library_file(
                file.path
            );

        if (
            result &&
            result.path
        ) {

            await openFromPath(
                result.path
            );
        }

    } catch (error) {

        console.error(
            "Error al abrir el archivo de biblioteca:",
            error
        );
    }
}


// =========================================================
// CARGAR BIBLIOTECA
// =========================================================

async function loadLibrary() {

    if (!apiExists("get_library")) {

        /*
         * Esto es normal durante el Paso 1.
         */

        libraryLocation.textContent =
            "Biblioteca no disponible todavía";

        renderLibrary([]);

        return;
    }


    try {

        const result =
            await window.pywebview.api.get_library();


        if (!result) {

            renderLibrary([]);

            return;
        }


        if (result.path) {

            libraryLocation.textContent =
                result.path;

        } else {

            libraryLocation.textContent =
                "Biblioteca no seleccionada";
        }


        renderLibrary(
            result.files || []
        );


    } catch (error) {

        console.error(
            "Error al cargar la biblioteca:",
            error
        );

        renderLibrary([]);
    }
}


// =========================================================
// ELEGIR CARPETA DE BIBLIOTECA
// =========================================================

async function chooseLibraryFolder() {

    await requestFullscreen();


    if (!apiExists("choose_library_folder")) {

        console.info(
            "choose_library_folder todavía no está disponible."
        );

        return;
    }


    try {

        const result =
            await window.pywebview.api.choose_library_folder();


        if (!result) {

            return;
        }


        if (result.path) {

            libraryLocation.textContent =
                result.path;
        }


        renderLibrary(
            result.files || []
        );


    } catch (error) {

        console.error(
            "Error al seleccionar la biblioteca:",
            error
        );
    }
}


// =========================================================
// ACTUALIZAR TEXTO DE CONTINUAR
// =========================================================

async function loadLastFileInfo() {

    if (!apiExists("get_last_file")) {

        continueFile.textContent =
            "No hay información del último archivo";

        continueButton.disabled =
            true;

        return;
    }


    try {

        const result =
            await window.pywebview.api.get_last_file();


        if (
            result &&
            result.path
        ) {

            state.lastFile =
                result;


            continueFile.textContent =
                result.name ||
                result.path;


            continueButton.disabled =
                false;

        } else {

            continueFile.textContent =
                "No hay un archivo reciente";

            continueButton.disabled =
                true;
        }


    } catch (error) {

        console.error(
            "Error obteniendo el último archivo:",
            error
        );

        continueButton.disabled =
            true;
    }
}


// =========================================================
// EVENTOS - INICIO
// =========================================================

continueButton.addEventListener(
    "click",
    continueLastFile
);


createButton.addEventListener(
    "click",
    createNewMap
);


libraryFolderButton.addEventListener(
    "click",
    chooseLibraryFolder
);


// =========================================================
// EVENTOS - ZOOM
// =========================================================

document
    .getElementById("zoom-in")
    .addEventListener(
        "click",
        () => {

            applyZoom(
                state.zoom + ZOOM_STEP
            );
        }
    );


document
    .getElementById("zoom-out")
    .addEventListener(
        "click",
        () => {

            applyZoom(
                state.zoom - ZOOM_STEP
            );
        }
    );


zoomInput.addEventListener(
    "change",
    () => {

        applyZoom(
            zoomInput.value
        );
    }
);


// =========================================================
// TECLADO
// =========================================================

document.addEventListener(
    "keydown",
    (event) => {

        const activeElement =
            document.activeElement;


        const tag =
            activeElement
                ? activeElement.tagName
                : "";


        /*
         * No capturamos las flechas mientras
         * el usuario está escribiendo en el
         * campo del zoom.
         */

        if (
            tag === "INPUT" ||
            tag === "TEXTAREA" ||
            tag === "SELECT"
        ) {

            return;
        }


        // -----------------------------------------
        // ESC
        // -----------------------------------------

        if (
            event.key === "Escape"
        ) {

            event.preventDefault();

            goBack();

            return;
        }


        // -----------------------------------------
        // IZQUIERDA
        // -----------------------------------------

        if (
            event.key === "ArrowLeft"
        ) {

            if (
                state.branchIndex !== null
            ) {

                event.preventDefault();

                goSibling(-1);
            }

            return;
        }


        // -----------------------------------------
        // DERECHA
        // -----------------------------------------

        if (
            event.key === "ArrowRight"
        ) {

            if (
                state.branchIndex !== null
            ) {

                event.preventDefault();

                goSibling(1);
            }

            return;
        }


        // -----------------------------------------
        // ARRIBA
        // -----------------------------------------

        if (
            event.key === "ArrowUp"
        ) {

            if (
                state.branchIndex !== null
            ) {

                event.preventDefault();

                stripEl.scrollBy({
                    top: -window.innerHeight * 0.75,
                    left: 0,
                    behavior: "smooth"
                });
            }

            return;
        }


        // -----------------------------------------
        // ABAJO
        // -----------------------------------------

        if (
            event.key === "ArrowDown"
        ) {

            if (
                state.branchIndex !== null
            ) {

                event.preventDefault();

                stripEl.scrollBy({
                    top: window.innerHeight * 0.75,
                    left: 0,
                    behavior: "smooth"
                });
            }

            return;
        }

    }
);


// =========================================================
// RUEDA DEL MOUSE
// =========================================================

/*
 * No interceptamos la rueda del mouse.
 *
 * El navegador se encarga directamente del
 * scroll vertical del visor.
 *
 * Esto es deliberado para mantener el
 * desplazamiento lo más fluido posible.
 */


// =========================================================
// INICIO DE LA APLICACIÓN
// =========================================================

async function initialize() {

    /*
     * Zoom inicial global.
     */

    applyZoom(
        ZOOM_DEFAULT
    );


    /*
     * Primero mostramos la pantalla inicial.
     */

    showHome();


    /*
     * Intentamos cargar la biblioteca.
     *
     * Durante el Paso 1 todavía puede no existir
     * get_library(). En ese caso simplemente queda
     * vacía.
     */

    await loadLibrary();


    /*
     * Averiguamos si existe un último archivo.
     */

    await loadLastFileInfo();


    /*
     * Compatibilidad con la versión actual:
     *
     * Si Python arrancó con un archivo ya abierto
     * y /manifest lo devuelve directamente,
     * lo cargamos.
     */

    const manifest =
        await fetchManifest();


    if (
        manifest &&
        manifest._path
    ) {

        await openFromPath(
            manifest._path
        );
    }
}


// =========================================================
// INICIO DE LA APLICACIÓN
// =========================================================

/*
 * pywebview expone window.pywebview.api
 * después de que la ventana termina de inicializarse.
 *
 * No debemos ejecutar initialize() solamente con
 * DOMContentLoaded porque en ese momento la API de
 * Python todavía puede no existir.
 */

window.addEventListener(
    "pywebviewready",
    initialize
);