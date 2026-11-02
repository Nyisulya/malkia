// Malkia Freight & Logistics - Global Seamless Async Interactivity Engine
// Zero Full-Page Reload Architecture for Internal Actions, Modals, Tabs & Inner Buttons

document.addEventListener('DOMContentLoaded', () => {
    initGlobalEngine();
});

function initGlobalEngine() {
    // 1. MODAL CONTROLLERS
    window.openModal = function(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            modal.classList.add('open');
            modal.style.display = 'flex';
            document.body.style.overflow = 'hidden';
            setTimeout(() => {
                const firstInput = modal.querySelector('input:not([type="hidden"]), select, textarea');
                if (firstInput) firstInput.focus();
            }, 100);
        }
    };

    window.closeModal = function(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            modal.classList.remove('open');
            modal.style.display = 'none';
            document.body.style.overflow = '';
        }
    };

    window.closeAllModals = function() {
        document.querySelectorAll('.modal-overlay').forEach(m => {
            m.classList.remove('open');
            m.style.display = 'none';
        });
        document.body.style.overflow = '';
    };

    // Close modal on clicking backdrop
    document.querySelectorAll('.modal-overlay').forEach(overlay => {
        if (!overlay.dataset.backdropBound) {
            overlay.dataset.backdropBound = 'true';
            overlay.addEventListener('click', (e) => {
                if (e.target === overlay) {
                    overlay.classList.remove('open');
                    overlay.style.display = 'none';
                    document.body.style.overflow = '';
                }
            });
        }
    });

    // Close modal on Escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            window.closeAllModals();
        }
    });

    // 2. FLOATING TOAST NOTIFICATION SYSTEM
    window.showToast = function(message, type = 'success', duration = 4500) {
        let container = document.getElementById('globalToastContainer');
        if (!container) {
            container = document.createElement('div');
            container.id = 'globalToastContainer';
            container.className = 'global-toast-container';
            container.style.cssText = 'position:fixed;top:1.25rem;right:1.25rem;z-index:999999;display:flex;flex-direction:column;gap:0.5rem;max-width:380px;pointer-events:none;';
            document.body.appendChild(container);
        }

        const toast = document.createElement('div');
        toast.className = `alert-toast floating-toast ${type}`;
        toast.style.cssText = 'pointer-events:auto;background:#FFFFFF;border-radius:10px;padding:0.85rem 1.15rem;box-shadow:0 10px 25px rgba(0,0,0,0.15);display:flex;align-items:center;justify-content:space-between;border-left:4px solid ' + 
            (type === 'error' || type === 'danger' ? '#DC2626' : (type === 'warning' ? '#D97706' : (type === 'info' ? '#2563EB' : '#16A34A'))) + ';margin-bottom:0.4rem;animation:slideInRight 0.3s ease forwards;';

        let iconColor = type === 'error' || type === 'danger' ? '#DC2626' : (type === 'warning' ? '#D97706' : (type === 'info' ? '#2563EB' : '#16A34A'));
        let iconHtml = `<i class="fa-solid fa-circle-check" style="color:${iconColor};"></i>`;
        if (type === 'error' || type === 'danger') {
            iconHtml = `<i class="fa-solid fa-circle-exclamation" style="color:${iconColor};"></i>`;
        } else if (type === 'warning') {
            iconHtml = `<i class="fa-solid fa-triangle-exclamation" style="color:${iconColor};"></i>`;
        } else if (type === 'info') {
            iconHtml = `<i class="fa-solid fa-circle-info" style="color:${iconColor};"></i>`;
        }

        toast.innerHTML = `
            <div style="display:flex;align-items:center;gap:0.65rem;">
                <span style="font-size:1.15rem;display:flex;">${iconHtml}</span>
                <span style="font-weight:700;font-size:0.85rem;color:#0F172A;">${message}</span>
            </div>
            <button type="button" style="background:none;border:none;cursor:pointer;color:#94A3B8;font-size:1.25rem;padding:0 0.35rem;margin-left:0.75rem;line-height:1;" onclick="this.closest('.alert-toast').remove()">&times;</button>
        `;

        container.appendChild(toast);

        setTimeout(() => {
            toast.style.transition = 'opacity 0.35s ease, transform 0.35s ease';
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(20px)';
            setTimeout(() => toast.remove(), 350);
        }, duration);
    };

    // Initialize existing django toasts
    document.querySelectorAll('.toast-messages-container .alert-toast').forEach(toast => {
        setTimeout(() => {
            toast.style.transition = 'opacity 0.4s ease, transform 0.4s ease';
            toast.style.opacity = '0';
            toast.style.transform = 'translateY(-10px)';
            setTimeout(() => toast.remove(), 400);
        }, 5000);
    });

    // 3. TAB SWITCHING ENGINE (ZERO RELOAD)
    window.switchTab = function(tabId, groupClass = 'tab-content-panel', navClass = 'tab-nav-btn') {
        document.querySelectorAll('.' + groupClass).forEach(el => {
            el.style.display = 'none';
        });

        document.querySelectorAll('.' + navClass).forEach(btn => {
            btn.classList.remove('active');
            if (btn.classList.contains('profile-tab-btn')) {
                btn.classList.remove('btn-primary');
                btn.classList.add('btn-outline');
            }
        });

        const activeTab = document.getElementById(tabId);
        if (activeTab) {
            activeTab.style.display = 'block';
        }

        const activeBtn = document.querySelector(`[data-target="${tabId}"]`);
        if (activeBtn) {
            activeBtn.classList.add('active');
            if (activeBtn.classList.contains('profile-tab-btn')) {
                activeBtn.classList.remove('btn-outline');
                activeBtn.classList.add('btn-primary');
            }
        }
    };

    // 4. MOBILE SIDEBAR DRAWER TOGGLE
    window.toggleMobileSidebar = function(forceClose = false) {
        const sidebar = document.querySelector('.app-sidebar');
        const backdrop = document.getElementById('sidebarBackdrop');
        if (!sidebar) return;

        if (forceClose || sidebar.classList.contains('mobile-open')) {
            sidebar.classList.remove('mobile-open');
            if (backdrop) backdrop.classList.remove('open');
            document.body.style.overflow = '';
        } else {
            sidebar.classList.add('mobile-open');
            if (backdrop) backdrop.classList.add('open');
            document.body.style.overflow = 'hidden';
        }
    };

    document.querySelectorAll('.app-sidebar .nav-item a').forEach(link => {
        link.addEventListener('click', () => {
            if (window.innerWidth <= 900) {
                window.toggleMobileSidebar(true);
            }
        });
    });

    // 5. PROGRESS BARS DYNAMIC FILL
    rebindDynamicElements();

    // 6. ROLE SWITCHER
    const roleSelect = document.getElementById('roleSwitcherSelect');
    if (roleSelect) {
        roleSelect.addEventListener('change', (e) => {
            const role = e.target.value;
            if (role) {
                window.location.href = `/switch-role/${role}/`;
            }
        });
    }

    // 7. GLOBAL ASYNC FORM SUBMISSION INTERCEPTOR (POST & GET)
    setupGlobalFormInterceptor();

    // 8. INNER LINK SPA NAVIGATOR (ZERO PAGE RELOAD FOR INNER BUTTONS)
    setupInnerLinkInterceptor();

    // 9. TABLE PAGINATION ENGINE
    window.initTablePagination();
}

// Rebind helpers after dynamic DOM replacement
function rebindDynamicElements() {
    document.querySelectorAll('.progress-bar-fill[data-width]').forEach(el => {
        el.style.width = el.getAttribute('data-width') + '%';
    });

    document.querySelectorAll('.alert-toast button').forEach(btn => {
        btn.onclick = function() {
            this.closest('.alert-toast').remove();
        };
    });

    document.querySelectorAll('.modal-overlay').forEach(overlay => {
        if (!overlay.dataset.backdropBound) {
            overlay.dataset.backdropBound = 'true';
            overlay.addEventListener('click', (e) => {
                if (e.target === overlay) {
                    overlay.classList.remove('open');
                    overlay.style.display = 'none';
                    document.body.style.overflow = '';
                }
            });
        }
    });

    if (window.initTablePagination) {
        window.initTablePagination();
    }
}

// Top visual progress bar
function showTopProgressBar() {
    let bar = document.getElementById('globalTopProgressBar');
    if (!bar) {
        bar = document.createElement('div');
        bar.id = 'globalTopProgressBar';
        bar.style.cssText = 'position:fixed;top:0;left:0;height:3px;background:linear-gradient(90deg,#2563EB,#10B981,#38BDF8);z-index:9999999;transition:width 0.25s ease;width:0%;box-shadow:0 0 10px rgba(37,99,235,0.7);';
        document.body.appendChild(bar);
    }
    bar.style.opacity = '1';
    bar.style.width = '35%';
    setTimeout(() => { if (bar && bar.style.width === '35%') bar.style.width = '75%'; }, 120);
}

function hideTopProgressBar() {
    const bar = document.getElementById('globalTopProgressBar');
    if (bar) {
        bar.style.width = '100%';
        setTimeout(() => {
            bar.style.opacity = '0';
            setTimeout(() => {
                bar.style.width = '0%';
            }, 300);
        }, 150);
    }
}

// Execute inline scripts within dynamically loaded DOM elements
function executeScripts(container) {
    if (!container) return;
    const scripts = container.querySelectorAll('script');
    scripts.forEach(oldScript => {
        const scriptType = (oldScript.getAttribute('type') || '').trim().toLowerCase();
        // Skip JSON data payloads (e.g. application/json) so they stay intact in DOM
        if (scriptType && scriptType !== 'text/javascript' && scriptType !== 'application/javascript' && scriptType !== 'module') {
            return;
        }
        const newScript = document.createElement('script');
        Array.from(oldScript.attributes).forEach(attr => {
            newScript.setAttribute(attr.name, attr.value);
        });
        newScript.textContent = oldScript.textContent;
        oldScript.parentNode.replaceChild(newScript, oldScript);
    });
}

// Sync extra_css and extra_js blocks across seamless AJAX navigation
function syncExtraCss(doc) {
    if (!doc) return;
    const newCss = doc.getElementById('dynamicExtraCss');
    const curCss = document.getElementById('dynamicExtraCss');
    if (newCss && curCss) {
        curCss.innerHTML = newCss.innerHTML;
    }
}

function syncExtraJs(doc) {
    if (!doc) return;
    const newJs = doc.getElementById('dynamicExtraJs');
    const curJs = document.getElementById('dynamicExtraJs');
    if (newJs && curJs) {
        curJs.innerHTML = newJs.innerHTML;
        executeScripts(curJs);
    }
}

// Update sidebar active link state dynamically
function updateActiveSidebarNav(url) {
    try {
        const pathname = new URL(url, window.location.origin).pathname;
        document.querySelectorAll('.app-sidebar .nav-item').forEach(item => {
            const link = item.querySelector('a');
            if (!link) return;
            const linkPath = new URL(link.href, window.location.origin).pathname;
            if (linkPath === pathname || (pathname.startsWith('/jobs/') && linkPath === '/jobs/')) {
                item.classList.add('active');
            } else if (pathname === linkPath) {
                item.classList.add('active');
            } else {
                item.classList.remove('active');
            }
        });
    } catch(e) {}
}

// Seamless Page Loader Engine (No full-page reload)
let isNavigating = false;
window.loadPageSeamlessly = async function(url, pushState = true) {
    if (isNavigating) return;
    isNavigating = true;
    showTopProgressBar();

    try {
        const response = await fetch(url, {
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        });

        if (!response.ok) {
            window.location.href = url;
            return;
        }

        const html = await response.text();
        const parser = new DOMParser();
        const doc = parser.parseFromString(html, 'text/html');

        if (doc.title) {
            document.title = doc.title;
        }

        const newContent = doc.querySelector('.page-content');
        const currentContent = document.querySelector('.page-content');

        if (newContent && currentContent) {
            currentContent.style.opacity = '0.35';
            currentContent.style.transition = 'opacity 0.12s ease';

            setTimeout(() => {
                syncExtraCss(doc);
                currentContent.innerHTML = newContent.innerHTML;
                executeScripts(currentContent);
                syncExtraJs(doc);
                currentContent.style.opacity = '1';

                rebindDynamicElements();
                window.closeAllModals();

                window.scrollTo({ top: 0, behavior: 'instant' });
            }, 80);
        } else {
            window.location.href = url;
            return;
        }

        updateActiveSidebarNav(url);

        if (pushState) {
            window.history.pushState({ url: url }, doc.title || '', url);
        }

    } catch (err) {
        console.error('Seamless Navigation Error:', err);
        window.location.href = url;
    } finally {
        isNavigating = false;
        hideTopProgressBar();
    }
};

// 8. INNER LINK SPA NAVIGATOR
function setupInnerLinkInterceptor() {
    document.addEventListener('click', (e) => {
        const link = e.target.closest('a');
        if (!link) return;

        // Skip sidebar links (allow normal navigation as user requested: "labda kama sidebar")
        if (link.closest('.app-sidebar')) return;

        // Skip target="_blank", print preview links, downloads
        if (link.target === '_blank' || link.hasAttribute('download')) return;
        if (link.getAttribute('data-no-ajax') === 'true' || link.getAttribute('data-native') === 'true') return;

        const href = link.getAttribute('href');
        if (!href || href.startsWith('#') || href.startsWith('javascript:') || href.startsWith('tel:') || href.startsWith('mailto:')) return;
        if (href.includes('/logout/') || href.includes('/static/') || href.includes('/media/')) return;

        // Same origin only
        if (link.origin !== window.location.origin) return;

        // Intercept inner link and load without page refresh!
        e.preventDefault();
        window.loadPageSeamlessly(link.href, true);
    });

    // Handle Browser Back & Forward buttons
    window.addEventListener('popstate', (e) => {
        const targetUrl = (e.state && e.state.url) ? e.state.url : window.location.href;
        window.loadPageSeamlessly(targetUrl, false);
    });
}

// 7. GLOBAL ASYNC FORM SUBMISSION INTERCEPTOR
function setupGlobalFormInterceptor() {
    let lastSubmitter = null;

    document.addEventListener('click', (e) => {
        const btn = e.target.closest('button[type="submit"], input[type="submit"]');
        if (btn) {
            lastSubmitter = btn;
        }
    }, true);

    document.addEventListener('submit', async (e) => {
        const form = e.target;
        if (!form || form.tagName !== 'FORM') return;

        if (form.getAttribute('data-no-ajax') === 'true') return;

        const action = form.getAttribute('action') || window.location.href;
        if (action.includes('/login/') || action.includes('/logout/')) return;

        const method = (form.getAttribute('method') || 'GET').toUpperCase();

        // Handle GET search/filter forms seamlessly without full page refresh!
        if (method === 'GET') {
            e.preventDefault();
            const url = new URL(action, window.location.origin);
            const formData = new FormData(form);
            for (const [key, val] of formData.entries()) {
                if (val) {
                    url.searchParams.set(key, val);
                } else {
                    url.searchParams.delete(key);
                }
            }
            window.loadPageSeamlessly(url.toString(), true);
            return;
        }

        // Handle POST action & modal forms seamlessly!
        e.preventDefault();

        const submitBtn = lastSubmitter || form.querySelector('button[type="submit"]');
        let originalBtnHtml = '';
        if (submitBtn) {
            originalBtnHtml = submitBtn.innerHTML;
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Saving...';
        }

        showTopProgressBar();

        try {
            const formData = new FormData(form);

            if (lastSubmitter && lastSubmitter.name && lastSubmitter.value) {
                formData.append(lastSubmitter.name, lastSubmitter.value);
            }

            const response = await fetch(action, {
                method: 'POST',
                body: formData,
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });

            const contentType = response.headers.get('content-type') || '';
            
            if (contentType.includes('application/json')) {
                const data = await response.json();
                if (data.success) {
                    window.showToast(data.message || 'Action completed successfully!', 'success');
                    window.closeAllModals();
                    form.reset();
                } else {
                    window.showToast(data.error || 'An error occurred, please try again.', 'error');
                }
            } else {
                const responseHtml = await response.text();
                const parser = new DOMParser();
                const doc = parser.parseFromString(responseHtml, 'text/html');

                // Extract Flash Messages and show them as floating toasts
                const messages = doc.querySelectorAll('.toast-messages-container .alert-toast');
                let foundMessage = false;
                messages.forEach(msg => {
                    const text = msg.querySelector('span') ? msg.querySelector('span').textContent.trim() : msg.textContent.trim();
                    let type = 'success';
                    if (msg.classList.contains('error') || msg.classList.contains('danger')) type = 'error';
                    else if (msg.classList.contains('warning')) type = 'warning';
                    else if (msg.classList.contains('info')) type = 'info';

                    window.showToast(text, type);
                    foundMessage = true;
                });

                if (!foundMessage && response.ok) {
                    window.showToast('Action completed successfully!', 'success');
                }

                // Close all open modals immediately
                window.closeAllModals();

                // Seamlessly update .page-content, extra_css, and extra_js without page refresh!
                const newContent = doc.querySelector('.page-content');
                const currentContent = document.querySelector('.page-content');
                if (newContent && currentContent) {
                    const newMessages = newContent.querySelector('.toast-messages-container');
                    if (newMessages) newMessages.remove();

                    syncExtraCss(doc);
                    currentContent.innerHTML = newContent.innerHTML;
                    executeScripts(currentContent);
                    syncExtraJs(doc);
                }

                if (doc.title) {
                    document.title = doc.title;
                }

                // Update URL history without page reload
                if (response.url && response.url !== window.location.href) {
                    window.history.pushState({ url: response.url }, doc.title || '', response.url);
                    updateActiveSidebarNav(response.url);
                }

                // Update sidebar badges from response HTML
                const newBadges = doc.querySelectorAll('.app-sidebar .nav-badge');
                newBadges.forEach(badge => {
                    const parentHref = badge.closest('a')?.getAttribute('href');
                    if (parentHref) {
                        const currentBadge = document.querySelector(`.app-sidebar a[href="${parentHref}"] .nav-badge`);
                        if (currentBadge) {
                            currentBadge.textContent = badge.textContent;
                        }
                    }
                });

                rebindDynamicElements();
            }
        } catch (error) {
            console.error('AJAX Action Error:', error);
            window.showToast('Unable to connect to system: ' + error.message, 'error');
        } finally {
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.innerHTML = originalBtnHtml;
            }
            lastSubmitter = null;
            hideTopProgressBar();
        }
    });
}

// 9. ZERO-RELOAD UNIVERSAL TABLE PAGINATION ENGINE
window.initTablePagination = function() {
    const tables = document.querySelectorAll('table.modern-table, table.containers-table, table.data-table, table[data-paginate="true"]');
    
    tables.forEach(table => {
        const tbody = table.querySelector('tbody');
        if (!tbody) return;

        let pageSize = parseInt(table.getAttribute('data-page-size') || '10', 10);
        if (isNaN(pageSize) || pageSize < 1) pageSize = 10;

        table.dataset.paginatedInitialized = 'true';
        if (!table.dataset.currentPage) {
            table.dataset.currentPage = '1';
        }
        table.dataset.pageSize = pageSize.toString();

        const parentWrap = table.closest('.table-responsive') || table.parentElement;
        let toolbar = parentWrap.nextElementSibling;
        if (!toolbar || !toolbar.classList.contains('table-pagination-toolbar')) {
            toolbar = document.createElement('div');
            toolbar.className = 'table-pagination-toolbar';
            parentWrap.insertAdjacentElement('afterend', toolbar);
        }
        table._paginationToolbar = toolbar;

        window.repaginateTable(table);
    });
};

window.repaginateTable = function(table, targetPage) {
    if (!table) return;
    const tbody = table.querySelector('tbody');
    if (!tbody) return;

    const toolbar = table._paginationToolbar || (table.closest('.table-responsive') || table.parentElement)?.nextElementSibling;
    if (!toolbar || !toolbar.classList.contains('table-pagination-toolbar')) return;

    const allRows = Array.from(tbody.querySelectorAll('tr')).filter(row => {
        return !row.querySelector('td[colspan]') && row.id !== 'noResultsRow';
    });

    const activeRows = allRows.filter(row => {
        return row.dataset.hiddenByFilter !== 'true' && row.getAttribute('data-filter-hidden') !== 'true';
    });

    const totalItems = activeRows.length;
    let pageSize = parseInt(table.dataset.pageSize || table.getAttribute('data-page-size') || '10', 10);
    const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));

    let currentPage = targetPage !== undefined ? targetPage : parseInt(table.dataset.currentPage || '1', 10);
    if (currentPage < 1) currentPage = 1;
    if (currentPage > totalPages) currentPage = totalPages;
    table.dataset.currentPage = currentPage.toString();

    const startIndex = (currentPage - 1) * pageSize;
    const endIndex = Math.min(startIndex + pageSize, totalItems);

    activeRows.forEach((row, idx) => {
        if (idx >= startIndex && idx < endIndex) {
            row.style.display = '';
        } else {
            row.style.display = 'none';
        }
    });

    const emptyRow = tbody.querySelector('tr td[colspan]')?.parentElement || tbody.querySelector('#noResultsRow');
    if (emptyRow) {
        emptyRow.style.display = (totalItems === 0) ? '' : 'none';
    }

    if (totalItems === 0) {
        toolbar.innerHTML = `
            <div class="pagination-info">
                <span>No records found in this list.</span>
            </div>
            <div class="pagination-controls"></div>
        `;
        return;
    }

    let numbersHtml = '';
    const maxVisiblePages = 5;
    let startPage = Math.max(1, currentPage - 2);
    let endPage = Math.min(totalPages, startPage + maxVisiblePages - 1);
    if (endPage - startPage < maxVisiblePages - 1) {
        startPage = Math.max(1, endPage - maxVisiblePages + 1);
    }

    if (startPage > 1) {
        numbersHtml += `<button type="button" class="pg-btn" data-page="1">1</button>`;
        if (startPage > 2) {
            numbersHtml += `<span class="pg-btn pg-ellipsis">&hellip;</span>`;
        }
    }

    for (let p = startPage; p <= endPage; p++) {
        numbersHtml += `<button type="button" class="pg-btn ${p === currentPage ? 'active' : ''}" data-page="${p}">${p}</button>`;
    }

    if (endPage < totalPages) {
        if (endPage < totalPages - 1) {
            numbersHtml += `<span class="pg-btn pg-ellipsis">&hellip;</span>`;
        }
        numbersHtml += `<button type="button" class="pg-btn" data-page="${totalPages}">${totalPages}</button>`;
    }

    toolbar.innerHTML = `
        <div class="pagination-info">
            Showing <strong>${startIndex + 1}</strong> to <strong>${endIndex}</strong> of <strong>${totalItems}</strong> entries
        </div>
        <div class="pagination-controls">
            <button type="button" class="pg-btn pg-prev" ${currentPage <= 1 ? 'disabled' : ''} title="Previous Page">
                <i class="fa-solid fa-chevron-left"></i> Prev
            </button>
            <div class="pg-numbers" style="display:inline-flex;gap:0.25rem;">
                ${numbersHtml}
            </div>
            <button type="button" class="pg-btn pg-next" ${currentPage >= totalPages ? 'disabled' : ''} title="Next Page">
                Next <i class="fa-solid fa-chevron-right"></i>
            </button>
        </div>
    `;

    toolbar.querySelector('.pg-prev')?.addEventListener('click', (e) => {
        e.preventDefault();
        if (currentPage > 1) {
            window.repaginateTable(table, currentPage - 1);
        }
    });

    toolbar.querySelector('.pg-next')?.addEventListener('click', (e) => {
        e.preventDefault();
        if (currentPage < totalPages) {
            window.repaginateTable(table, currentPage + 1);
        }
    });

    toolbar.querySelectorAll('.pg-numbers .pg-btn[data-page]').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            const p = parseInt(btn.getAttribute('data-page'), 10);
            if (!isNaN(p) && p !== currentPage) {
                window.repaginateTable(table, p);
            }
        });
    });
};


// =========================================================================
// MALKIA CARGO WAVE - REAL-TIME COLLABORATIVE AUTO-SYNC ENGINE
// Real-time synchronization across all ~7 staff consoles & clients without manual page refresh
// =========================================================================
(function initMalkiaRealtimeSync() {
    let lastVersion = null;
    let isReloading = false;
    let pendingReload = false;

    function isUserEditing() {
        const openModal = document.querySelector('.modal.open, .modal[style*="display: flex"], .modal[style*="display: block"]');
        if (openModal) return true;

        const active = document.activeElement;
        if (active && ['INPUT', 'TEXTAREA', 'SELECT'].includes(active.tagName)) {
            return true;
        }
        return false;
    }

    async function checkPulse() {
        if (document.hidden || isReloading) return;

        try {
            const url = '/api/realtime-pulse/?v=' + encodeURIComponent(lastVersion || '');
            const res = await fetch(url, {
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            });
            if (!res.ok) return;

            const data = await res.json();
            if (!lastVersion) {
                lastVersion = data.version;
                return;
            }

            if (data.has_change && data.version !== lastVersion) {
                lastVersion = data.version;

                // 1. Sleek Floating Toast Notification for the update
                if (data.latest_event && data.latest_event.details) {
                    const evt = data.latest_event;
                    const actor = evt.actor || 'Operations';
                    const toastText = `⚡ <strong>${actor}</strong>: ${evt.details}`;
                    if (window.showToast) {
                        window.showToast(toastText, 'info');
                    }
                }

                // 2. Real-time badge counter update
                if (data.counts) {
                    const finBadges = document.querySelectorAll('.finance-badge-count, #sidebarFinanceBadge');
                    finBadges.forEach(b => {
                        const cnt = data.counts.pending_finance || 0;
                        b.textContent = cnt;
                        b.style.display = cnt > 0 ? 'inline-flex' : 'none';
                    });
                }

                // 3. Auto-Reload current view seamlessly
                if (isUserEditing()) {
                    pendingReload = true;
                } else {
                    seamlessContentReload();
                }
            }
        } catch (e) {
            // Quiet network recovery
        }
    }

    async function seamlessContentReload() {
        if (isReloading) return;
        isReloading = true;
        pendingReload = false;

        const pill = document.getElementById('malkiaLiveSyncPill');
        if (pill) {
            pill.style.background = '#EFF6FF';
            pill.style.borderColor = '#BFDBFE';
            pill.style.color = '#1D4ED8';
            const dot = pill.querySelector('span');
            if (dot) dot.style.background = '#2563EB';
        }

        try {
            const targetUrl = window.location.href;
            const res = await fetch(targetUrl, {
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            });

            if (res.ok) {
                const html = await res.text();
                const parser = new DOMParser();
                const doc = parser.parseFromString(html, 'text/html');

                const newContent = doc.querySelector('.page-content');
                const currentContent = document.querySelector('.page-content');

                if (newContent && currentContent) {
                    currentContent.style.transition = 'opacity 0.15s ease';
                    currentContent.style.opacity = '0.5';

                    setTimeout(() => {
                        // Remove flash messages from new content to avoid repeating past alerts
                        const newMsgs = newContent.querySelector('.toast-messages-container');
                        if (newMsgs) newMsgs.remove();

                        currentContent.innerHTML = newContent.innerHTML;
                        if (typeof executeScripts === 'function') executeScripts(currentContent);
                        if (typeof rebindDynamicElements === 'function') rebindDynamicElements();

                        currentContent.style.opacity = '1';
                        isReloading = false;
                    }, 120);
                } else {
                    isReloading = false;
                }
            } else {
                isReloading = false;
            }
        } catch (err) {
            isReloading = false;
        } finally {
            setTimeout(() => {
                if (pill) {
                    pill.style.background = '#ECFDF5';
                    pill.style.borderColor = '#A7F3D0';
                    pill.style.color = '#065F46';
                    const dot = pill.querySelector('span');
                    if (dot) dot.style.background = '#10B981';
                }
            }, 600);
        }
    }

    // Trigger reload once user finishes typing or closes modal
    document.addEventListener('focusout', () => {
        if (pendingReload && !isUserEditing()) {
            setTimeout(() => {
                if (!isUserEditing()) seamlessContentReload();
            }, 400);
        }
    });

    // Check every 3.5 seconds
    setInterval(checkPulse, 3500);
})();
