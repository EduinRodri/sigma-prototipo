/* SIGMA — comportamiento mínimo, sin librerías. Todo es mejora: sin JS la app funciona igual. */
(function () {
  "use strict";
  var quieto = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* Tablas → tarjetas en celular: cada celda toma su rótulo del encabezado. */
  document.querySelectorAll(".tabla table").forEach(function (t) {
    var rotulos = Array.prototype.map.call(t.querySelectorAll("thead th"), function (th) { return th.textContent.trim(); });
    t.querySelectorAll("tbody tr").forEach(function (tr) {
      Array.prototype.forEach.call(tr.children, function (td, i) { if (rotulos[i]) td.setAttribute("data-label", rotulos[i]); });
    });
  });


  /* Botón flotante: al bajar se encoge a solo el icono (el texto sigue para el lector de pantalla). */
  var fab = document.querySelector(".boton.principal");
  if (fab) {
    var ultimo = window.scrollY;
    window.addEventListener("scroll", function () {
      var y = window.scrollY;
      if (y > ultimo + 6 && y > 80) fab.classList.add("compacto");
      else if (y < ultimo - 6 || y < 80) fab.classList.remove("compacto");
      ultimo = y;
    }, { passive: true });
  }

  /* Menú de administración (fondo, reportes, catálogos): botón de la cabecera en celular. */
  var menu = document.querySelector(".menu");
  var botonesMenu = document.querySelectorAll(".mas-boton, .menu-gestion");
  if (menu && botonesMenu.length) {
    var marcar = function (abierto) {
      menu.classList.toggle("abierto", abierto);
      botonesMenu.forEach(function (b) { b.setAttribute("aria-expanded", abierto ? "true" : "false"); });
    };
    botonesMenu.forEach(function (b) {
      b.addEventListener("click", function (e) { e.stopPropagation(); marcar(!menu.classList.contains("abierto")); });
    });
    document.addEventListener("click", function (e) { if (!menu.contains(e.target)) marcar(false); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") marcar(false); });
  }

  /* Avisos: se cierran solos (los de error se quedan hasta que se cierren). */
  document.querySelectorAll(".avisos .mensaje").forEach(function (m) {
    var quitar = function () {
      if (quieto) { m.remove(); return; }
      m.classList.add("saliendo");
      setTimeout(function () { m.remove(); }, 320);
    };
    var x = m.querySelector(".cerrar");
    if (x) x.addEventListener("click", quitar);
    if (!m.classList.contains("error")) setTimeout(quitar, 6000);
  });

  /* Cifras que cuentan hasta su valor ($1.234.567 o 12). */
  if (!quieto) {
    document.querySelectorAll(".cifra .valor").forEach(function (el) {
      var m = el.textContent.trim().match(/^(-?\$?)([\d.]+)$/);
      if (!m) return;
      var fin = parseInt(m[2].replace(/\./g, ""), 10);
      if (!fin || fin < 2) return;
      el.dataset.valor = fin;
      var prefijo = m[1], t0 = null, dur = 700;
      var formato = function (n) { return prefijo + String(n).replace(/\B(?=(\d{3})+(?!\d))/g, "."); };
      var paso = function (t) {
        if (t0 === null) t0 = t;
        var p = Math.min((t - t0) / dur, 1), e = 1 - Math.pow(1 - p, 3);
        el.textContent = formato(Math.round(fin * e));
        if (p < 1) requestAnimationFrame(paso); else el.textContent = formato(fin);
      };
      el.textContent = formato(0);
      requestAnimationFrame(paso);
    });
  }

  /* Botones de envío: evitan el doble clic mientras el servidor (gratis) despierta. */
  document.querySelectorAll("form").forEach(function (f) {
    f.addEventListener("submit", function (e) {
      var b = e.submitter;
      if (b && b.classList.contains("boton")) setTimeout(function () { b.classList.add("cargando"); }, 0);
    });
  });

  /* Ingreso: mostrar/ocultar la contraseña y usuarios de prueba con un toque. */
  var ver = document.querySelector(".ver-clave"), clave = document.getElementById("id_password");
  if (ver && clave) {
    ver.hidden = false;
    ver.addEventListener("click", function () {
      var oculta = clave.type === "password";
      clave.type = oculta ? "text" : "password";
      ver.setAttribute("aria-pressed", oculta ? "true" : "false");
      ver.setAttribute("aria-label", oculta ? "Ocultar contraseña" : "Mostrar contraseña");
    });
  }
  document.querySelectorAll("[data-usuario]").forEach(function (b) {
    b.addEventListener("click", function () {
      var u = document.getElementById("id_username");
      if (!u) return;
      u.value = b.getAttribute("data-usuario");
      if (clave) clave.focus();
    });
  });

  /* Vista previa del soporte (foto del celular). */
  /* Botón «Tomar la foto con la cámara»: la foto pasa al campo de soporte, que también admite PDF desde archivos. */
  document.querySelectorAll("input[data-camara]").forEach(function (cam) {
    cam.addEventListener("change", function () {
      var destino = document.getElementById(cam.getAttribute("data-camara"));
      if (!destino || !cam.files.length || typeof DataTransfer === "undefined") return;
      var dt = new DataTransfer();
      dt.items.add(cam.files[0]);
      destino.files = dt.files;
      destino.dispatchEvent(new Event("change", { bubbles: true }));
      cam.value = "";
    });
  });

  document.querySelectorAll("input[type=file]:not([data-camara])").forEach(function (inp) {
    var img = null;
    inp.addEventListener("change", function () {
      var f = inp.files && inp.files[0];
      if (f && f.type.indexOf("image/") === 0) {
        if (!img) {
          img = document.createElement("img");
          img.className = "vista-soporte"; img.alt = "Vista previa del soporte";
          inp.insertAdjacentElement("afterend", img);
        }
        img.src = URL.createObjectURL(f); img.classList.add("visible");
      } else if (img) { img.classList.remove("visible"); }
    });
  });

  /* Carrusel de la pantalla de ingreso: solo rota las fotos visibles (en celular las verticales, en PC las horizontales). */
  var diapos = document.querySelectorAll(".carrusel .diapositiva");
  if (diapos.length > 1) {
    var visibles = function () {
      return Array.prototype.filter.call(diapos, function (d) { return d.offsetParent !== null; });
    };
    var actual = function () {
      var v = visibles();
      for (var k = 0; k < v.length; k++) if (v[k].classList.contains("activa")) return k;
      return -1;
    };
    var primera = visibles();
    if (primera.length && actual() === -1) primera[0].classList.add("activa");
    setInterval(function () {
      var v = visibles(), k = actual();
      if (v.length < 2) return;
      if (k >= 0) v[k].classList.remove("activa");
      v[(k + 1) % v.length].classList.add("activa");
    }, 6000);
  }

  /* Atrás en móvil: del rastro de migas queda solo «‹ Anterior». */
  var migas = document.querySelector(".migas");
  if (migas) {
    var enlaces = migas.querySelectorAll("a");
    var ult = enlaces[enlaces.length - 1];
    if (ult) {
      var atras = document.createElement("a");
      atras.className = "atras"; atras.href = ult.href; atras.textContent = ult.textContent;
      migas.insertBefore(atras, migas.firstChild);
      migas.classList.add("con-atras");
    }
  }

  /* Búsqueda desde el icono del celular. */
  if (location.hash === "#buscar") {
    var campo = document.querySelector(".barra-tabla input[type=search]");
    if (campo) campo.focus();
  }

  /* Tarjeta completa pulsable en las listas. */
  document.querySelectorAll(".tabla tbody tr").forEach(function (tr) {
    var a = tr.querySelector("a.id");
    if (!a) return;
    tr.classList.add("tocable");
    tr.addEventListener("click", function (e) {
      if (e.target.closest("a, button")) return;
      a.click();
    });
  });

  /* Transiciones: barra de progreso y, si el servidor tarda, pantalla de espera. */
  var barra = document.querySelector(".progreso");
  var espera = document.querySelector(".espera");
  var temporizador;
  function navegando() {
    if (barra) { barra.classList.remove("corre"); void barra.offsetWidth; barra.classList.add("corre"); }
    clearTimeout(temporizador);
    temporizador = setTimeout(function () { if (espera) espera.classList.add("visible"); }, 1200);
  }
  window.addEventListener("pageshow", function () {
    clearTimeout(temporizador);
    if (barra) barra.classList.remove("corre");
    if (espera) espera.classList.remove("visible");
    document.querySelectorAll(".boton.cargando").forEach(function (b) { b.classList.remove("cargando"); });
  });
  document.addEventListener("click", function (e) {
    var a = e.target.closest("a[href]");
    if (!a || e.defaultPrevented || e.metaKey || e.ctrlKey || e.shiftKey || a.target === "_blank") return;
    var u = new URL(a.href, location.href);
    if (u.origin !== location.origin || (u.pathname === location.pathname && u.search === location.search)) return;
    navegando();
  });
  document.addEventListener("submit", function (e) { if (!e.defaultPrevented) navegando(); });

  /* Confirmación antes de acciones que no se deshacen (hoja inferior en celular). */
  var dialogo;
  document.addEventListener("click", function (e) {
    var b = e.target.closest("button[data-confirmar]");
    if (!b || !b.form || b.dataset.confirmado) return;
    if (!window.HTMLDialogElement) return;
    e.preventDefault();
    if (!dialogo) {
      dialogo = document.createElement("dialog");
      dialogo.className = "confirmar";
      dialogo.innerHTML = '<h3>¿Seguro?</h3><p></p><div class="acciones"><button type="button" class="boton secundario" data-no>Volver</button><button type="button" class="boton peligro" data-si></button></div>';
      document.body.appendChild(dialogo);
    }
    dialogo.querySelector("p").textContent = b.dataset.confirmar;
    dialogo.querySelector("[data-si]").textContent = b.dataset.ok || "Confirmar";
    dialogo.querySelector("[data-no]").onclick = function () { dialogo.close(); };
    dialogo.querySelector("[data-si]").onclick = function () {
      dialogo.close();
      b.dataset.confirmado = "1";
      b.form.requestSubmit(b);
    };
    dialogo.showModal();
  });

  /* App instalable: el service worker solo guarda estáticos (ver templates/sw.js). */
  /* Solo en https (producción): en desarrollo un worker serviría estáticos viejos. */
  if ("serviceWorker" in navigator && location.protocol === "https:") {
    navigator.serviceWorker.register("/sw.js").catch(function () {});
  }
  /* Tema claro/oscuro: sigue al sistema hasta que la persona elige. */
  var btnTema = document.querySelector(".tema");
  if (btnTema) btnTema.addEventListener("click", function () {
    var raiz = document.documentElement;
    var oscuro = raiz.dataset.tema ? raiz.dataset.tema === "oscuro" : window.matchMedia("(prefers-color-scheme: dark)").matches;
    var nuevo = oscuro ? "claro" : "oscuro";
    raiz.dataset.tema = nuevo;
    try { localStorage.setItem("sigma-tema", nuevo); } catch (e) {}
  });
  /* Teclado en PC: «/» busca; «g» y una letra navegan (i inicio, a anticipos, p por aprobar, f flota). */
  var destinos = { i: "inicio", a: "anticipos", p: "pendientes", f: "flota" };
  var esperaG = false;
  document.addEventListener("keydown", function (e) {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    var t = e.target, escribiendo = t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName));
    if (escribiendo) { if (e.key === "Escape") t.blur(); return; }
    if (e.key === "/") {
      var b = document.querySelector(".superior .buscador input");
      if (b && b.offsetParent) { e.preventDefault(); b.focus(); }
      return;
    }
    if (esperaG) {
      esperaG = false;
      var enlace = document.querySelector('.menu a[href][data-ir="' + e.key + '"]');
      if (enlace) enlace.click();
      return;
    }
    if (e.key === "g") { esperaG = true; setTimeout(function () { esperaG = false; }, 1200); }
  });
  /* Monto del gasto: teclado numérico, valor en pesos legible y aviso si pasa de lo disponible. */
  var monto = document.querySelector("input[name=monto]");
  if (monto) {
    monto.setAttribute("inputmode", "numeric");
    var eco = document.createElement("div");
    eco.className = "equivale"; eco.setAttribute("aria-live", "polite");
    monto.insertAdjacentElement("afterend", eco);
    var dispEl = document.querySelector(".lado .cifra .valor");
    var disp = dispEl ? parseInt(dispEl.dataset.valor || dispEl.textContent.replace(/\D/g, ""), 10) : null;
    var pesos = function (n) { return "$" + String(n).replace(/\B(?=(\d{3})+(?!\d))/g, "."); };
    var mostrar = function () {
      var n = parseInt(monto.value.replace(/\D/g, ""), 10);
      eco.classList.remove("excede");
      if (!n) { eco.textContent = ""; return; }
      if (disp !== null && n > disp) { eco.textContent = pesos(n) + " supera lo disponible (" + pesos(disp) + "): no se aceptará."; eco.classList.add("excede"); }
      else eco.textContent = "= " + pesos(n);
    };
    monto.addEventListener("input", mostrar); mostrar();
  }
  /* Accesibilidad: iconos decorativos fuera del lector de pantalla y página actual marcada en el menú. */
  document.querySelectorAll("svg.icono, svg.logo-cliente").forEach(function (s) { s.setAttribute("aria-hidden", "true"); s.setAttribute("focusable", "false"); });
  document.querySelectorAll(".menu a.activo").forEach(function (a) { a.setAttribute("aria-current", "page"); });
  document.querySelectorAll(".pestanas a.activo").forEach(function (a) { a.setAttribute("aria-current", "true"); });
  /* Guía de diseño: demostración del aviso (toast). */
  var demo = document.querySelector("[data-guia=aviso]");
  if (demo) demo.addEventListener("click", function () {
    var cont = document.querySelector(".avisos");
    if (!cont) { cont = document.createElement("div"); cont.className = "avisos"; document.body.appendChild(cont); }
    var m = document.createElement("div");
    m.className = "mensaje success"; m.setAttribute("role", "status");
    m.innerHTML = '<svg class="icono" aria-hidden="true"><use href="#i-ok"/></svg><span>Así se ve un aviso: se cierra solo a los 6 segundos.</span><button type="button" class="cerrar" aria-label="Cerrar aviso">&times;</button>';
    cont.appendChild(m);
    var quitar = function () { m.classList.add("saliendo"); setTimeout(function () { m.remove(); }, 320); };
    m.querySelector(".cerrar").addEventListener("click", quitar);
    setTimeout(quitar, 6000);
  });
})();
