/* =============================================================================
   PALDACA · Activos UI Kit — comportamiento
   Sin dependencias más allá de Bootstrap 5 (Offcanvas / Modal).
   Todo es mejora progresiva: si el JS falla, los formularios nativos siguen
   funcionando (el <select> real permanece en el DOM y las URLs son reales).
   ============================================================================= */
(function () {
    'use strict';

    var REDUCED = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    function $(sel, ctx) { return (ctx || document).querySelector(sel); }
    function $$(sel, ctx) { return Array.prototype.slice.call((ctx || document).querySelectorAll(sel)); }

    function debounce(fn, wait) {
        var t;
        return function () {
            var args = arguments, self = this;
            clearTimeout(t);
            t = setTimeout(function () { fn.apply(self, args); }, wait);
        };
    }

    function escapeHtml(str) {
        return String(str).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }

    /* Iniciales y tono pastel deterministas — mismo criterio que el filtro Python,
       para que un avatar pintado en cliente coincida con el del servidor. */
    function iniciales(nombre) {
        var partes = String(nombre || '').trim().split(/\s+/).filter(Boolean);
        if (!partes.length) return '??';
        if (partes.length === 1) return partes[0].substring(0, 2).toUpperCase();
        return (partes[0][0] + partes[partes.length - 1][0]).toUpperCase();
    }

    function tonoAvatar(nombre) {
        var s = String(nombre || ''), h = 0;
        for (var i = 0; i < s.length; i++) { h = (h * 31 + s.charCodeAt(i)) >>> 0; }
        return h % 8;
    }

    /* -------------------------------------------------------------------------
       1. Contadores animados de los KPI
       ---------------------------------------------------------------------- */
    function initContadores() {
        var nodos = $$('.ax-count[data-value]');
        if (!nodos.length) return;

        if (REDUCED) {
            nodos.forEach(function (n) { n.textContent = n.dataset.value; });
            return;
        }

        var animar = function (nodo) {
            var destino = parseInt(nodo.dataset.value, 10) || 0;
            var inicio = performance.now();
            var dur = Math.min(1100, 380 + destino * 5);

            function frame(now) {
                var p = Math.min(1, (now - inicio) / dur);
                var eased = 1 - Math.pow(1 - p, 3);
                nodo.textContent = Math.round(destino * eased).toLocaleString('es-VE');
                if (p < 1) requestAnimationFrame(frame);
            }
            requestAnimationFrame(frame);
        };

        if (!('IntersectionObserver' in window)) { nodos.forEach(animar); return; }

        var obs = new IntersectionObserver(function (entradas) {
            entradas.forEach(function (e) {
                if (e.isIntersecting) { animar(e.target); obs.unobserve(e.target); }
            });
        }, { threshold: 0.4 });

        nodos.forEach(function (n) { obs.observe(n); });
    }

    /* -------------------------------------------------------------------------
       2. Combobox de personas / ubicaciones sobre un <select> nativo
       ---------------------------------------------------------------------- */
    function crearCombo(contenedor) {
        var select = $('select.ax-combo-native', contenedor);
        if (!select || contenedor.dataset.comboReady === '1') return null;
        contenedor.dataset.comboReady = '1';

        var opciones = Array.prototype.map.call(select.options, function (o) {
            return { value: o.value, label: o.textContent.trim() };
        }).filter(function (o) { return o.label !== ''; });

        var vacia = contenedor.dataset.comboEmptyLabel || 'Sin asignar';
        // Normaliza la opción vacía del ModelChoiceField ("---------").
        opciones = opciones.map(function (o) {
            return o.value === '' ? { value: '', label: vacia } : o;
        });

        var input = document.createElement('input');
        input.type = 'text';
        input.className = 'ax-combo-input';
        input.setAttribute('role', 'combobox');
        input.setAttribute('aria-autocomplete', 'list');
        input.setAttribute('aria-expanded', 'false');
        input.autocomplete = 'off';
        input.placeholder = contenedor.dataset.comboPlaceholder || 'Escribe para buscar…';

        var lista = document.createElement('ul');
        lista.className = 'ax-combo-list';
        lista.setAttribute('role', 'listbox');
        lista.hidden = true;

        // El <select> real sigue siendo el control enviado y validado: se oculta
        // visualmente pero permanece enfocable, para que la validación nativa
        // del navegador no quede atrapada en un elemento inalcanzable.
        select.classList.add('is-enhanced');
        select.setAttribute('tabindex', '-1');
        contenedor.appendChild(input);
        contenedor.appendChild(lista);

        select.addEventListener('invalid', function () {
            input.focus();
            input.classList.add('is-invalid');
        });

        var activo = -1;
        var visibles = [];

        function etiquetaActual() {
            var op = opciones.filter(function (o) { return o.value === select.value; })[0];
            return op ? op.label : vacia;
        }

        function sincronizarInput() { input.value = etiquetaActual(); }

        function resaltar(label, q) {
            if (!q) return escapeHtml(label);
            var i = label.toLowerCase().indexOf(q.toLowerCase());
            if (i < 0) return escapeHtml(label);
            return escapeHtml(label.slice(0, i)) +
                '<mark>' + escapeHtml(label.slice(i, i + q.length)) + '</mark>' +
                escapeHtml(label.slice(i + q.length));
        }

        function pintar(q) {
            var term = (q || '').trim().toLowerCase();
            visibles = term
                ? opciones.filter(function (o) { return o.label.toLowerCase().indexOf(term) >= 0; })
                : opciones.slice();

            if (!visibles.length) {
                lista.innerHTML = '<li class="ax-combo-empty"><i class="bi bi-search"></i> Sin coincidencias</li>';
                return;
            }

            lista.innerHTML = visibles.map(function (o, i) {
                var esVacia = o.value === '';
                var av = esVacia
                    ? '<span class="ax-avatar" aria-hidden="true"><i class="bi bi-person-dash"></i></span>'
                    : '<span class="ax-avatar ax-avatar--c' + tonoAvatar(o.label) + '" aria-hidden="true">' +
                      escapeHtml(iniciales(o.label)) + '</span>';
                return '<li class="ax-combo-option' + (i === activo ? ' is-active' : '') + '"' +
                    ' role="option" data-value="' + escapeHtml(o.value) + '"' +
                    ' aria-selected="' + (o.value === select.value) + '">' +
                    av + '<span>' + resaltar(o.label, q) + '</span></li>';
            }).join('');
        }

        function abrir() {
            activo = -1;
            pintar('');
            lista.hidden = false;
            input.setAttribute('aria-expanded', 'true');
            input.select();
        }

        function cerrar() {
            lista.hidden = true;
            input.setAttribute('aria-expanded', 'false');
            sincronizarInput();
        }

        function elegir(valor) {
            select.value = valor;
            select.dispatchEvent(new Event('change', { bubbles: true }));
            cerrar();
        }

        input.addEventListener('focus', abrir);
        input.addEventListener('input', function () { activo = -1; pintar(input.value); lista.hidden = false; });

        input.addEventListener('keydown', function (e) {
            if (lista.hidden && (e.key === 'ArrowDown' || e.key === 'Enter')) { abrir(); return; }
            if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
                e.preventDefault();
                if (!visibles.length) return;
                activo = e.key === 'ArrowDown'
                    ? (activo + 1) % visibles.length
                    : (activo - 1 + visibles.length) % visibles.length;
                pintar(input.value);
                var act = $('.ax-combo-option.is-active', lista);
                if (act) act.scrollIntoView({ block: 'nearest' });
            } else if (e.key === 'Enter') {
                if (activo >= 0 && visibles[activo]) { e.preventDefault(); elegir(visibles[activo].value); }
            } else if (e.key === 'Escape') {
                cerrar();
            }
        });

        lista.addEventListener('mousedown', function (e) {
            var op = e.target.closest('.ax-combo-option');
            if (!op) return;
            e.preventDefault();
            elegir(op.dataset.value);
        });

        document.addEventListener('click', function (e) {
            if (!contenedor.contains(e.target)) cerrar();
        });

        sincronizarInput();

        var api = {
            setValue: function (v) { select.value = v == null ? '' : String(v); sincronizarInput(); },
            focus: function () { input.focus(); },
            label: etiquetaActual,
            select: select,
            // Permite que un alta express aparezca sin recargar la página
            agregarOpcion: function (valor, etiqueta) {
                if (!opciones.some(function (o) { return o.value === String(valor); })) {
                    opciones.push({ value: String(valor), label: etiqueta });
                    opciones.sort(function (a, b) {
                        if (a.value === '') return -1;
                        if (b.value === '') return 1;
                        return a.label.localeCompare(b.label, 'es');
                    });
                }
                sincronizarInput();
            }
        };
        contenedor._axCombo = api;
        return api;
    }

    function initCombos() { $$('.ax-combo').forEach(crearCombo); }

    /* -------------------------------------------------------------------------
       3. Vista previa "De → Para" dentro del drawer
       ---------------------------------------------------------------------- */
    function pintarPersona(nodo, nombre) {
        if (!nodo) return;
        var vacio = !nombre || nombre === 'Sin asignar';
        nodo.className = 'ax-person' + (vacio ? ' ax-person--empty' : '');
        nodo.innerHTML =
            '<span class="ax-avatar ' + (vacio ? '' : 'ax-avatar--c' + tonoAvatar(nombre)) + '" aria-hidden="true">' +
            (vacio ? '<i class="bi bi-person-dash"></i>' : escapeHtml(iniciales(nombre))) +
            '</span><span class="ax-person-name">' + escapeHtml(vacio ? 'Sin asignar' : nombre) + '</span>';
    }

    function pintarTexto(nodo, texto, iconoVacio) {
        if (!nodo) return;
        var vacio = !texto;
        nodo.className = 'ax-person' + (vacio ? ' ax-person--empty' : '');
        nodo.innerHTML =
            '<span class="ax-avatar" aria-hidden="true"><i class="bi ' +
            (vacio ? (iconoVacio || 'bi-dash') : 'bi-geo-alt') + '"></i></span>' +
            '<span class="ax-person-name">' + escapeHtml(texto || 'Sin definir') + '</span>';
    }

    /* -------------------------------------------------------------------------
       4. Drawers de reasignación / reubicación individuales
       ---------------------------------------------------------------------- */
    function initDrawers() {
        [
            { drawer: '#drawerReasignar', trigger: '[data-ax-reasignar]', campo: 'usuario' },
            { drawer: '#drawerReubicar', trigger: '[data-ax-reubicar]', campo: 'ubicacion' }
        ].forEach(function (cfg) {
            var drawer = $(cfg.drawer);
            if (!drawer) return;

            var form = $('form', drawer);
            var combo = $('.ax-combo', drawer);
            var submit = $('[data-ax-submit]', drawer);

            document.addEventListener('click', function (e) {
                var btn = e.target.closest(cfg.trigger);
                if (!btn) return;
                e.preventDefault();

                var d = btn.dataset;
                form.setAttribute('action', d.url);

                // Cabecera: qué activo se está moviendo (previene el error humano nº1)
                var codigo = $('[data-ax-fill="codigo"]', drawer);
                var equipo = $('[data-ax-fill="equipo"]', drawer);
                var serial = $('[data-ax-fill="serial"]', drawer);
                var tipo = $('[data-ax-fill="tipo"]', drawer);
                if (codigo) codigo.textContent = d.codigo || '';
                if (equipo) equipo.textContent = d.equipo || '';
                if (tipo) tipo.className = 'bi ' + (d.icono || 'bi-box-seam');
                if (serial) {
                    serial.textContent = d.serial || 'Sin número de serie';
                    serial.classList.toggle('text-muted', !d.serial);
                }

                var actual = cfg.campo === 'usuario' ? (d.usuarioNombre || '') : (d.ubicacionNombre || '');
                var actualId = cfg.campo === 'usuario' ? (d.usuarioId || '') : (d.ubicacionId || '');

                var origen = $('[data-ax-fill="origen"]', drawer);
                if (cfg.campo === 'usuario') pintarPersona(origen, actual);
                else pintarTexto(origen, actual);

                if (combo && combo._axCombo) {
                    // El origen queda anotado en el propio <select>: así el botón
                    // de guardar sabe si hubo cambio real o no.
                    combo._axCombo.select.dataset.axOrigenId = actualId;
                    combo._axCombo.setValue(actualId);
                    actualizarDestino(drawer, cfg.campo, combo._axCombo);
                }

                if (submit) submit.disabled = true;

                bootstrap.Offcanvas.getOrCreateInstance(drawer).show();
                setTimeout(function () { if (combo && combo._axCombo) combo._axCombo.focus(); }, 260);
            });

            if (combo) {
                var api = crearCombo(combo) || combo._axCombo;
                if (api) {
                    api.select.addEventListener('change', function () {
                        actualizarDestino(drawer, cfg.campo, api);
                    });
                }
            }

            // Evita doble envío: bloquea el botón y muestra progreso
            if (form) {
                form.addEventListener('submit', function () {
                    if (submit) {
                        submit.disabled = true;
                        submit.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Guardando…';
                    }
                });
            }
        });
    }

    function actualizarDestino(drawer, campo, api) {
        var destino = $('[data-ax-fill="destino"]', drawer);
        var submit = $('[data-ax-submit]', drawer);
        var aviso = $('[data-ax-fill="aviso"]', drawer);
        var origenId = api.select.dataset.axOrigenId;
        var etiqueta = api.label();

        if (campo === 'usuario') pintarPersona(destino, api.select.value ? etiqueta : '');
        else pintarTexto(destino, api.select.value ? etiqueta : '');

        // Solo se habilita si realmente hay un cambio: nada de "guardar" en falso.
        var sinCambio = String(api.select.value || '') === String(origenId || '');
        if (submit) submit.disabled = sinCambio;
        if (aviso) aviso.hidden = !sinCambio;
    }

    /* -------------------------------------------------------------------------
       5. Modo selección + barra de acciones en lote
       ---------------------------------------------------------------------- */
    function initSeleccion() {
        var tabla = $('[data-ax-tabla]');
        var bar = $('#axBulkBar');
        if (!tabla || !bar) return;

        var toggle = $('#axToggleSeleccion');
        var selectAll = $('#axSelectAll');
        var contador = $('[data-ax-bulk-count]');
        var checks = function () { return $$('.ax-check', tabla); };
        var seleccionados = function () { return checks().filter(function (c) { return c.checked; }); };
        var modo = false;

        function refrescar() {
            var n = seleccionados().length;
            bar.hidden = n === 0;
            if (contador) contador.textContent = n;
            checks().forEach(function (c) {
                c.closest('tr').classList.toggle('is-selected', c.checked);
            });
            if (selectAll) {
                var total = checks().length;
                selectAll.checked = n > 0 && n === total;
                selectAll.indeterminate = n > 0 && n < total;
            }
            $$('[data-ax-bulk-label]').forEach(function (el) {
                el.textContent = el.dataset.axBulkLabel.replace('{n}', n);
            });
        }

        function activarModo(on) {
            modo = on;
            $$('.ax-col-check', tabla).forEach(function (c) { c.hidden = !on; });
            if (!on) { checks().forEach(function (c) { c.checked = false; }); }
            if (toggle) {
                toggle.classList.toggle('btn-pastel--lila', on);
                toggle.classList.toggle('btn-pastel--neutro', !on);
                toggle.innerHTML = on
                    ? '<i class="bi bi-x-lg"></i> Salir de selección'
                    : '<i class="bi bi-check2-square"></i> Seleccionar';
            }
            refrescar();
        }

        if (toggle) toggle.addEventListener('click', function () { activarModo(!modo); });

        if (selectAll) {
            selectAll.addEventListener('change', function () {
                checks().forEach(function (c) { c.checked = selectAll.checked; });
                refrescar();
            });
        }

        tabla.addEventListener('change', function (e) {
            if (e.target.classList.contains('ax-check')) refrescar();
        });

        $('[data-ax-bulk-clear]') && $('[data-ax-bulk-clear]').addEventListener('click', function () {
            activarModo(false);
        });

        // Inyecta los IDs seleccionados en cualquier formulario de lote al enviar
        $$('[data-ax-bulk-form]').forEach(function (form) {
            form.addEventListener('submit', function (e) {
                $$('input[data-ax-generated]', form).forEach(function (i) { i.remove(); });
                var ids = seleccionados();
                if (!ids.length) {
                    e.preventDefault();
                    alert('Selecciona al menos un activo.');
                    return;
                }
                ids.forEach(function (c) {
                    var h = document.createElement('input');
                    h.type = 'hidden';
                    h.name = form.dataset.axBulkForm; // p. ej. "activos" o "activos_seleccionados"
                    h.value = c.value;
                    h.setAttribute('data-ax-generated', '1');
                    form.appendChild(h);
                });
            });
        });

        activarModo(false);
    }

    /* -------------------------------------------------------------------------
       6. Buscador: atajo "/" y envío con retardo
       ---------------------------------------------------------------------- */
    function initBuscador() {
        // Los selects de filtro aplican al instante: un cambio = un resultado.
        // Va primero y suelto, porque hay listados con filtro pero sin buscador.
        $$('select[data-ax-autofiltro]').forEach(function (s) {
            s.addEventListener('change', function () {
                if (s.form) s.form.requestSubmit();
            });
        });

        var input = $('[data-ax-buscar]');
        if (!input) return;

        document.addEventListener('keydown', function (e) {
            var enCampo = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName);
            if (e.key === '/' && !enCampo && !e.metaKey && !e.ctrlKey) {
                e.preventDefault();
                input.focus();
                input.select();
            }
            if (e.key === 'Escape' && document.activeElement === input) input.blur();
        });

        if (!input.form) return;

        var auto = debounce(function () {
            if (input.value.length === 0 || input.value.length >= 2) input.form.requestSubmit();
        }, 550);

        input.addEventListener('input', auto);
    }

    /* -------------------------------------------------------------------------
       7. Stepper del formulario de alta
       ---------------------------------------------------------------------- */
    function initStepper() {
        var raiz = $('[data-ax-stepper]');
        if (!raiz) return;

        var pasos = $$('.ax-step', raiz);
        var lineas = $$('.ax-step-line', raiz);
        var paneles = $$('[data-ax-panel]');
        var form = $('#axFormActivo');
        var actual = 0;

        function mostrar(i) {
            actual = i;
            paneles.forEach(function (p, k) { p.hidden = k !== i; });
            pasos.forEach(function (p, k) {
                p.classList.toggle('is-active', k === i);
                p.classList.toggle('is-done', k < i);
            });
            lineas.forEach(function (l, k) { l.classList.toggle('is-done', k < i); });
            $$('[data-ax-step-prev]').forEach(function (b) { b.hidden = i === 0; });
            $$('[data-ax-step-next]').forEach(function (b) { b.hidden = i >= paneles.length - 1; });
            $$('[data-ax-step-submit]').forEach(function (b) { b.hidden = i < paneles.length - 1; });
            if (!REDUCED) raiz.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }

        function validarPanel(i) {
            var panel = paneles[i];
            var campos = $$('input, select, textarea', panel).filter(function (c) { return c.required; });
            for (var k = 0; k < campos.length; k++) {
                if (!campos[k].checkValidity()) { campos[k].reportValidity(); return false; }
            }
            return true;
        }

        $$('[data-ax-step-next]').forEach(function (b) {
            b.addEventListener('click', function () { if (validarPanel(actual)) mostrar(actual + 1); });
        });

        $$('[data-ax-step-prev]').forEach(function (b) {
            b.addEventListener('click', function () { mostrar(actual - 1); });
        });

        pasos.forEach(function (p, i) {
            p.addEventListener('click', function () {
                if (i <= actual || validarPanel(actual)) mostrar(i);
            });
        });

        // Enter en un paso intermedio avanza; no envía a medio llenar.
        if (form) {
            form.addEventListener('keydown', function (e) {
                if (e.key !== 'Enter') return;
                if (e.target.tagName === 'TEXTAREA') return;
                if (actual >= paneles.length - 1) return;
                e.preventDefault();
                if (validarPanel(actual)) mostrar(actual + 1);
            });
        }

        // Si el servidor devolvió errores, abre el paso que los contiene
        if (form) {
            var conError = paneles.findIndex(function (p) { return $('.ax-error', p); });
            mostrar(conError >= 0 ? conError : 0);
        } else {
            mostrar(0);
        }
    }

    /* -------------------------------------------------------------------------
       8. Modal de eliminación
       Una sola pieza para todo el módulo: confirmar no cuesta una navegación.
       ---------------------------------------------------------------------- */
    function initEliminar() {
        var modal = $('#modalEliminar');
        if (!modal) return;

        var form = $('form', modal);
        var input = $('[data-ax-confirm-field]', modal);
        var boton = $('[data-ax-confirm-submit]', modal);
        var esperado = '';

        function campo(nombre) { return $('[data-ax-fill="' + nombre + '"]', modal); }

        function mostrar(nombre, texto) {
            var nodo = campo(nombre);
            if (!nodo) return;
            nodo.textContent = texto || '';
            nodo.hidden = !texto;
        }

        function comprobar() {
            if (!esperado) { boton.disabled = false; return; }
            var ok = input.value.trim().toUpperCase() === esperado;
            boton.disabled = !ok;
            input.classList.toggle('is-valid', ok);
            input.classList.toggle('is-invalid', input.value.length > 0 && !ok);
        }

        if (input) input.addEventListener('input', comprobar);

        document.addEventListener('click', function (e) {
            var btn = e.target.closest('[data-ax-eliminar]');
            if (!btn) return;
            e.preventDefault();

            var d = btn.dataset;
            form.setAttribute('action', d.url);

            mostrar('titulo', d.titulo || '¿Confirmas la eliminación?');
            mostrar('ficha', d.ficha || '');
            mostrar('aviso', d.aviso || '');
            mostrar('impacto', d.impacto || '');
            mostrar('bloqueado', d.bloqueado || '');

            var codigo = campo('codigo');
            if (codigo) {
                codigo.textContent = d.codigo || '';
                codigo.hidden = !d.codigo;
            }
            var icono = campo('icono');
            if (icono) icono.className = 'bi ' + (d.icono || 'bi-trash3');

            // Si algo lo bloquea (dependencias), el modal solo informa.
            var bloqueado = !!d.bloqueado;
            esperado = bloqueado ? '' : (d.confirmar || '').trim().toUpperCase();

            var wrap = campo('confirmar-wrap');
            if (wrap) wrap.hidden = !esperado;
            var textoConfirmar = campo('confirmar-texto');
            if (textoConfirmar) textoConfirmar.textContent = d.confirmar || '';
            if (input) {
                input.value = '';
                input.classList.remove('is-valid', 'is-invalid');
            }

            boton.hidden = bloqueado;
            comprobar();

            bootstrap.Modal.getOrCreateInstance(modal).show();
            if (esperado) setTimeout(function () { input.focus(); }, 400);
        });

        form.addEventListener('submit', function () {
            boton.disabled = true;
            boton.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Eliminando…';
        });
    }

    /* -------------------------------------------------------------------------
       9. Alta express de catálogo (categoría / subcategoría / ubicación)
       Evita el peor tramo del flujo: salir del formulario de activos para ir a
       crear un catálogo y volver.
       ---------------------------------------------------------------------- */
    function initCrearRapido() {
        var modal = $('#modalCrearRapido');
        if (!modal) return;

        var form = $('form[data-ax-crear]', modal);
        var submit = $('[data-ax-crear-submit]', modal);
        var cajaErrores = $('[data-ax-fill="errores"]', modal);
        var destino = null;

        function panelesVisibles(tipo) {
            $$('[data-pane]', modal).forEach(function (pane) {
                var activo = pane.dataset.pane === tipo;
                pane.hidden = !activo;
                // Los campos ocultos NO deben viajar en el envío: hay un
                // `nombre` por panel y se pisarían entre sí.
                $$('input, select, textarea', pane).forEach(function (campo) {
                    campo.disabled = !activo;
                });
            });
            sincronizarModoCategoria();
        }

        function sincronizarModoCategoria() {
            var paneSub = $('[data-pane="subcategoria"]', modal);
            if (!paneSub || paneSub.hidden) return;
            var nueva = $('#axModoCatNueva', modal).checked;
            $$('[data-modo]', paneSub).forEach(function (bloque) {
                var activo = bloque.dataset.modo === (nueva ? 'nueva' : 'existente');
                bloque.hidden = !activo;
                $$('input, select', bloque).forEach(function (c) { c.disabled = !activo; });
            });
        }

        $$('input[name="axModoCategoria"]', modal).forEach(function (r) {
            r.addEventListener('change', sincronizarModoCategoria);
        });

        // El prefijo se propone solo a partir del nombre: menos tecleo, menos error
        var campoNombreSub = $('[data-ax-sugiere-prefijo]', modal);
        if (campoNombreSub) {
            var prefijo = $(campoNombreSub.dataset.axSugierePrefijo, modal);
            var preview = $('[data-ax-fill="preview-prefijo"]', modal);
            campoNombreSub.addEventListener('input', function () {
                if (!prefijo.dataset.tocado) {
                    prefijo.value = campoNombreSub.value
                        .normalize('NFD').replace(/[̀-ͯ]/g, '')
                        .replace(/[^a-zA-Z0-9]/g, '')
                        .substring(0, 3).toUpperCase();
                }
                if (preview) preview.textContent = prefijo.value || 'XXX';
            });
            prefijo.addEventListener('input', function () {
                prefijo.dataset.tocado = '1';
                if (preview) preview.textContent = prefijo.value.toUpperCase() || 'XXX';
            });
        }

        function pintarErrores(errores) {
            if (!errores) { cajaErrores.hidden = true; return; }
            var lineas = Object.keys(errores).map(function (campo) {
                return '<div>' + escapeHtml([].concat(errores[campo]).join(' ')) + '</div>';
            });
            cajaErrores.innerHTML = '<i class="bi bi-exclamation-octagon"></i><div>' + lineas.join('') + '</div>';
            cajaErrores.hidden = false;
        }

        document.addEventListener('click', function (e) {
            var btn = e.target.closest('[data-ax-crear-abrir]');
            if (!btn) return;
            e.preventDefault();

            destino = document.querySelector(btn.dataset.target);
            form.setAttribute('action', btn.dataset.url);
            $('[data-ax-fill="titulo"]', modal).textContent = btn.dataset.titulo || 'Alta rápida';

            form.reset();
            var pf = $('#axRapidoPrefijo', modal);
            if (pf) delete pf.dataset.tocado;
            pintarErrores(null);
            panelesVisibles(btn.dataset.tipo);

            bootstrap.Modal.getOrCreateInstance(modal).show();
            setTimeout(function () {
                var primero = $('[data-pane="' + btn.dataset.tipo + '"] input:not([disabled])', modal);
                if (primero) primero.focus();
            }, 400);
        });

        form.addEventListener('submit', function (e) {
            e.preventDefault();
            pintarErrores(null);
            submit.disabled = true;
            var original = submit.innerHTML;
            submit.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Creando…';

            fetch(form.action, {
                method: 'POST',
                body: new FormData(form),
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
                credentials: 'same-origin'
            })
                .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, data: d }; }); })
                .then(function (res) {
                    if (!res.ok || !res.data.ok) {
                        pintarErrores(res.data.errores || { __all__: ['No se pudo crear.'] });
                        return;
                    }
                    if (destino) {
                        var existente = destino.querySelector('option[value="' + res.data.id + '"]');
                        if (!existente) {
                            existente = new Option(res.data.texto, res.data.id);
                            destino.add(existente);
                        }
                        destino.value = res.data.id;
                        destino.dispatchEvent(new Event('change', { bubbles: true }));

                        var contenedor = destino.closest('.ax-combo');
                        if (contenedor && contenedor._axCombo) {
                            contenedor._axCombo.agregarOpcion(res.data.id, res.data.texto);
                            contenedor._axCombo.setValue(res.data.id);
                        }
                        destino.classList.add('is-valid');
                    }
                    bootstrap.Modal.getOrCreateInstance(modal).hide();
                })
                .catch(function () {
                    pintarErrores({ __all__: ['Error de red. Revisa tu conexión e inténtalo de nuevo.'] });
                })
                .finally(function () {
                    submit.disabled = false;
                    submit.innerHTML = original;
                });
        });
    }

    /* -------------------------------------------------------------------------
       10. Dropdowns que escapan del scroll horizontal de la tabla
       Popper posiciona en `absolute` por defecto, así que el menú de una fila
       queda recortado por el `overflow-x` del contenedor. Con estrategia
       `fixed` sale del recorte y se ve completo.
       ---------------------------------------------------------------------- */
    function initDropdowns() {
        if (!window.bootstrap || !bootstrap.Dropdown) return;
        $$('[data-bs-toggle="dropdown"]').forEach(function (el) {
            bootstrap.Dropdown.getOrCreateInstance(el, {
                popperConfig: function (config) {
                    return Object.assign({}, config, { strategy: 'fixed' });
                }
            });
        });
    }

    /* -------------------------------------------------------------------------
       11. Índices de escalonado (stagger) automáticos
       ---------------------------------------------------------------------- */
    function initStagger() {
        $$('[data-ax-stagger]').forEach(function (grupo) {
            var hijos = grupo.children;
            var max = parseInt(grupo.dataset.axStagger, 10) || 30;
            for (var i = 0; i < hijos.length && i < max; i++) {
                // El escalonado se corta en 10: con 25 filas, un retardo lineal
                // dejaría la última casi un segundo invisible. Es decoración,
                // no puede retrasar la lectura.
                hijos[i].style.setProperty('--i', Math.min(i, 10));
            }
        });
    }

    /* ---------------------------------------------------------------------- */
    document.addEventListener('DOMContentLoaded', function () {
        initStagger();
        initContadores();
        initCombos();
        initDrawers();
        initSeleccion();
        initBuscador();
        initStepper();
        initEliminar();
        initCrearRapido();
        initDropdowns();
    });
})();
