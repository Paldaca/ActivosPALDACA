/* =============================================================================
   PALDACA · Etiquetas QR — listado, filtros y selección para impresión
   ============================================================================= */
(function () {
    'use strict';

    var STORAGE_KEY = 'ax-etiquetas-seleccion';
    var MOBILE_QUERY = '(max-width: 767.98px)';
    var HINT_DEFAULT = 'Toca las tarjetas para marcarlas. Puedes mezclar subcategorías.';
    var HINT_LIMIT = 'Llegaste al máximo por PDF. Imprime o quita alguna para seguir.';

    function $(sel, ctx) {
        return (ctx || document).querySelector(sel);
    }

    function $$(sel, ctx) {
        return Array.prototype.slice.call((ctx || document).querySelectorAll(sel));
    }

    function initFiltrosEstado() {
        var hiddenEstado = $('#axEtiquetaEstadoHidden');
        var selectEstado = $('#ax-etiqueta-estado');
        if (!hiddenEstado || !selectEstado) return;

        function syncCamposEstado() {
            var esMovil = window.matchMedia(MOBILE_QUERY).matches;
            hiddenEstado.disabled = esMovil;
            selectEstado.disabled = !esMovil;
        }

        syncCamposEstado();
        window.addEventListener('resize', syncCamposEstado);
    }

    function initFiltroCategoria() {
        var formFiltros = $('#axEtiquetaFiltros');
        var catSelect = $('#id_categoria');
        if (!catSelect || !formFiltros) return;

        catSelect.addEventListener('change', function () {
            var subSelect = $('#id_subcategoria');
            if (subSelect) subSelect.value = '';
            formFiltros.submit();
        });
    }

    function initGenerarEtiquetasForm() {
        var form = $('#drawerGenerarEtiquetas form');
        if (!form) return;

        form.addEventListener('submit', function () {
            var boton = form.querySelector('button[type="submit"]');
            if (boton) {
                boton.disabled = true;
                boton.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Generando…';
            }
            setTimeout(function () {
                window.location.reload();
            }, 600);
        });
    }

    function initSeleccionEtiquetas() {
        var page = $('.ax-etiqueta-page');
        var selMode = $('#axEtiquetaSelMode');
        if (!page || !selMode) return;

        var maxSel = parseInt(selMode.dataset.max, 10) || 80;
        var pdfBase = selMode.dataset.pdfUrl || '';
        var toggleBtn = $('#axEtiquetaToggleSel');
        var btnExit = $('#axEtiquetaSelExit');
        var btnCancel = $('#axEtiquetaSelCancel');
        var btnClear = $('#axEtiquetaSelClear');
        var selbar = $('#axEtiquetaSelbar');
        var selCount = $('#axEtiquetaSelCount');
        var selBadge = $('#axEtiquetaSelBadge');
        var selLabel = $('#axEtiquetaSelLabel');
        var selProgress = $('#axEtiquetaSelProgress');
        var selHint = $('#axEtiquetaSelHint');
        var btnPrint = $('#axEtiquetaImprimirSel');
        var chkAllPage = $('#axEtiquetaSelAllPage');
        var checkboxes = $$('.ax-etiqueta-sel');
        var cards = $$('.ax-etiqueta-card.is-selectable');
        var modoActivo = false;

        function leerSeleccion() {
            try {
                var raw = sessionStorage.getItem(STORAGE_KEY);
                var parsed = raw ? JSON.parse(raw) : [];
                return Array.isArray(parsed) ? parsed.map(String) : [];
            } catch (e) {
                return [];
            }
        }

        function guardarSeleccion(ids) {
            sessionStorage.setItem(STORAGE_KEY, JSON.stringify(ids));
        }

        function esInteractivo(target) {
            return !!target.closest('a, button, input, select, textarea, label, form, .dropdown-menu');
        }

        function sincronizarUi() {
            var ids = leerSeleccion();
            var total = ids.length;
            var alLimite = total >= maxSel;

            checkboxes.forEach(function (chk) {
                chk.checked = ids.indexOf(chk.value) !== -1;
                var card = chk.closest('.ax-etiqueta-card');
                if (card) card.classList.toggle('is-selected', chk.checked);
            });

            if (selMode) selMode.hidden = !modoActivo;
            if (selCount) selCount.textContent = String(total);
            if (selBadge) selBadge.textContent = String(total);
            if (selLabel) {
                selLabel.textContent = total === 1 ? 'etiqueta lista' : 'etiquetas listas';
            }
            if (selProgress) {
                selProgress.style.width = Math.min(100, (total / maxSel) * 100) + '%';
            }
            if (selHint) {
                selHint.textContent = alLimite ? HINT_LIMIT : HINT_DEFAULT;
                selHint.classList.toggle('is-limit', alLimite);
            }

            if (selbar) selbar.hidden = !modoActivo || total === 0;

            if (btnPrint) {
                if (total > 0) {
                    btnPrint.href = pdfBase + '?ids=' + ids.join(',');
                    btnPrint.removeAttribute('aria-disabled');
                } else {
                    btnPrint.href = '#';
                    btnPrint.setAttribute('aria-disabled', 'true');
                }
            }

            if (toggleBtn) {
                toggleBtn.classList.toggle('btn-pastel--lila', modoActivo);
                toggleBtn.classList.toggle('btn-pastel--neutro', !modoActivo);
                toggleBtn.innerHTML = modoActivo
                    ? '<i class="bi bi-x-lg"></i> Salir de selección'
                    : '<i class="bi bi-check2-square"></i> Seleccionar e imprimir';
            }

            if (chkAllPage) {
                var visibles = checkboxes.filter(function (c) { return !c.disabled; });
                var marcadas = visibles.filter(function (c) { return c.checked; });
                chkAllPage.indeterminate = marcadas.length > 0 && marcadas.length < visibles.length;
                chkAllPage.checked = visibles.length > 0 && marcadas.length === visibles.length;
            }
        }

        function alternarId(id, activo) {
            var ids = leerSeleccion();
            var idx = ids.indexOf(id);
            if (activo) {
                if (idx !== -1) return true;
                if (ids.length >= maxSel) return false;
                ids.push(id);
            } else if (idx !== -1) {
                ids.splice(idx, 1);
            }
            guardarSeleccion(ids);
            sincronizarUi();
            return true;
        }

        function activarModo(on, limpiar) {
            modoActivo = on;
            page.classList.toggle('is-sel-mode', on);
            if (!on && limpiar !== false) {
                guardarSeleccion([]);
            }
            sincronizarUi();
        }

        cards.forEach(function (card) {
            card.addEventListener('click', function (e) {
                if (!modoActivo || esInteractivo(e.target)) return;
                var chk = card.querySelector('.ax-etiqueta-sel');
                if (!chk) return;
                if (!alternarId(chk.value, !chk.checked) && !chk.checked) {
                    if (selHint) {
                        selHint.textContent = HINT_LIMIT;
                        selHint.classList.add('is-limit');
                    }
                }
            });
        });

        checkboxes.forEach(function (chk) {
            chk.addEventListener('change', function () {
                if (!modoActivo) return;
                if (!alternarId(chk.value, chk.checked)) {
                    chk.checked = false;
                }
            });
        });

        if (toggleBtn) {
            toggleBtn.addEventListener('click', function () {
                activarModo(!modoActivo);
            });
        }

        [btnExit, btnCancel].forEach(function (btn) {
            if (!btn) return;
            btn.addEventListener('click', function () {
                activarModo(false);
            });
        });

        if (btnClear) {
            btnClear.addEventListener('click', function () {
                guardarSeleccion([]);
                sincronizarUi();
            });
        }

        if (chkAllPage) {
            chkAllPage.addEventListener('change', function () {
                var ids = leerSeleccion();
                var visibles = checkboxes.filter(function (c) { return !c.disabled; });

                if (chkAllPage.checked) {
                    visibles.forEach(function (chk) {
                        if (ids.indexOf(chk.value) === -1 && ids.length < maxSel) {
                            ids.push(chk.value);
                        }
                    });
                } else {
                    visibles.forEach(function (chk) {
                        var idx = ids.indexOf(chk.value);
                        if (idx !== -1) ids.splice(idx, 1);
                    });
                }

                guardarSeleccion(ids);
                sincronizarUi();
            });
        }

        activarModo(leerSeleccion().length > 0, false);
    }

    document.addEventListener('DOMContentLoaded', function () {
        initFiltrosEstado();
        initFiltroCategoria();
        initGenerarEtiquetasForm();
        initSeleccionEtiquetas();
    });
}());
