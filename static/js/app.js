// Malkia Freight & Logistics - Global Seamless Async Interactivity Engine
// Zero Full-Page Reload Architecture for Internal Actions, Modals, Tabs & Inner Buttons

const loadedExternalScripts = new Set();
const pageCleanups = [];

window.registerPageCleanup = function(callback) {
    if (typeof callback === 'function') pageCleanups.push(callback);
};

function cleanupCurrentPage() {
    while (pageCleanups.length) {
        const cleanup = pageCleanups.pop();
        try { cleanup(); } catch (err) {}
    }
}

document.addEventListener('DOMContentLoaded', () => {
    initGlobalEngine();
});

function initGlobalEngine() {
    Array.from(document.scripts).forEach(script => {
        if (script.src) loadedExternalScripts.add(script.src);
    });

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
    setupLinkPrefetch();
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
    setTimeout(() => { if (bar && bar.style.width === '35%') bar.style.width = '75%'; }, 80);
}

function hideTopProgressBar() {
    const bar = document.getElementById('globalTopProgressBar');
    if (bar) {
        bar.style.width = '100%';
        setTimeout(() => {
            bar.style.opacity = '0';
            setTimeout(() => {
                bar.style.width = '0%';
            }, 180);
        }, 80);
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
        if (oldScript.src) {
            if (loadedExternalScripts.has(oldScript.src)) {
                oldScript.remove();
                return;
            }
            loadedExternalScripts.add(oldScript.src);
        }
        const newScript = document.createElement('script');
        Array.from(oldScript.attributes).forEach(attr => {
            newScript.setAttribute(attr.name, attr.value);
        });
        if (newScript.src) newScript.async = false;
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
        const parsedUrl = new URL(url, window.location.origin);
        const pathname = parsedUrl.pathname;
        const currentTab = parsedUrl.searchParams.get('tab');

        document.querySelectorAll('.app-sidebar .nav-item').forEach(item => {
            const link = item.querySelector('a');
            if (!link) return;
            const linkUrl = new URL(link.href, window.location.origin);
            const linkPath = linkUrl.pathname;
            const linkTab = linkUrl.searchParams.get('tab');

            let isActive = false;
            if (linkTab) {
                isActive = (linkPath === pathname && linkTab === (currentTab || 'vehicles'));
            } else {
                isActive = (linkPath === pathname || (pathname.startsWith('/jobs/') && linkPath === '/jobs/'));
            }

            item.classList.toggle('active', isActive);
        });
    } catch(e) {}
}

const PAGE_CACHE_TTL = 20000;
const PAGE_CACHE_LIMIT = 12;
const pageCache = new Map();
const inFlightFetches = new Map();
let activePrefetches = 0;
let isNavigating = false;
let activeNavController = null;
let activeNavId = 0;

const NON_AJAX_PATH_PATTERNS = [
    '/api/',
    '/login/',
    '/logout/',
    '/static/',
    '/media/',
    '/export',
    '/download',
    '/print-',
    '/print/',
    '/switch-role/',
    '/payslip/',
    '/id-card/',
    '/view/',
];

function isNonAjaxPath(pathname) {
    return NON_AJAX_PATH_PATTERNS.some(pattern => pathname.includes(pattern));
}

function isCacheablePageUrl(url) {
    try {
        const parsed = new URL(url, window.location.origin);
        return parsed.origin === window.location.origin &&
            !isNonAjaxPath(parsed.pathname) &&
            !parsed.searchParams.has('edit');
    } catch (err) {
        return false;
    }
}

function getCachedPage(url) {
    const key = new URL(url, window.location.origin).href;
    const entry = pageCache.get(key);
    if (!entry) return null;
    if (Date.now() - entry.fetchedAt > PAGE_CACHE_TTL) {
        pageCache.delete(key);
        return null;
    }
    pageCache.delete(key);
    pageCache.set(key, entry);
    return entry.doc;
}

function cachePage(url, doc) {
    if (!isCacheablePageUrl(url) || !doc.querySelector('.page-content')) return;
    const key = new URL(url, window.location.origin).href;
    pageCache.delete(key);
    while (pageCache.size >= PAGE_CACHE_LIMIT) {
        pageCache.delete(pageCache.keys().next().value);
    }
    pageCache.set(key, { doc: doc, fetchedAt: Date.now() });
}

window.clearPageCache = function() {
    pageCache.clear();
};

async function fetchPageDocument(url, signal = null) {
    const fetchOpts = {
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
    };
    if (signal) fetchOpts.signal = signal;
    const response = await fetch(url, fetchOpts);
    if (!response.ok) throw new Error('Page request failed');
    if (response.redirected && new URL(response.url).pathname.startsWith('/login/')) {
        throw new Error('Session expired');
    }
    const html = await response.text();
    const doc = new DOMParser().parseFromString(html, 'text/html');
    if (!doc.querySelector('.page-content')) throw new Error('Not a portal page');
    return doc;
}

function renderPageDocument(doc, url, options = {}) {
    const newContent = doc.querySelector('.page-content');
    const currentContent = document.querySelector('.page-content');
    if (!newContent || !currentContent) return false;

    cleanupCurrentPage();
    window.closeAllModals();
    syncExtraCss(doc);
    currentContent.innerHTML = newContent.innerHTML;
    executeScripts(currentContent);
    syncExtraJs(doc);
    rebindDynamicElements();

    if (doc.title) document.title = doc.title;
    currentContent.style.opacity = '1';
    currentContent.style.transition = '';
    updateActiveSidebarNav(url);
    if (options.scrollTop !== false) window.scrollTo({ top: 0, behavior: 'instant' });
    return true;
}

window.loadPageSeamlessly = async function(url, pushState = true) {
    const targetUrl = new URL(url, window.location.origin).href;
    if (activeNavController) {
        try { activeNavController.abort(); } catch (e) {}
        activeNavController = null;
    }

    const navId = ++activeNavId;
    const controller = new AbortController();
    activeNavController = controller;
    isNavigating = true;

    try {
        let doc = getCachedPage(targetUrl);
        if (!doc) {
            showTopProgressBar();
            const existingInFlight = inFlightFetches.get(targetUrl);
            if (existingInFlight) {
                doc = await existingInFlight;
            } else {
                const fetchPromise = fetchPageDocument(targetUrl, controller.signal);
                inFlightFetches.set(targetUrl, fetchPromise);
                try {
                    doc = await fetchPromise;
                    cachePage(targetUrl, doc);
                } finally {
                    inFlightFetches.delete(targetUrl);
                }
            }
        }

        if (navId !== activeNavId || controller.signal.aborted) {
            return;
        }

        if (!renderPageDocument(doc, targetUrl)) {
            window.location.href = targetUrl;
            return;
        }

        if (pushState && window.location.href !== targetUrl) {
            window.history.pushState({ url: targetUrl }, doc.title || '', targetUrl);
        }
    } catch (err) {
        if (err && err.name === 'AbortError') return;
        if (navId !== activeNavId) return;
        console.error('Seamless Navigation Error:', err);
        window.location.href = targetUrl;
    } finally {
        if (navId === activeNavId) {
            isNavigating = false;
            activeNavController = null;
            hideTopProgressBar();
            window.dispatchEvent(new Event('malkia:navigation-complete'));
        }
    }
};

function setupInnerLinkInterceptor() {
    document.addEventListener('click', (e) => {
        if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
        const link = e.target.closest('a');
        if (!link) return;

        if (link.target === '_blank' || link.hasAttribute('download')) return;
        if (link.getAttribute('data-no-ajax') === 'true' || link.getAttribute('data-native') === 'true') return;

        const href = link.getAttribute('href');
        if (!href || href.startsWith('#') || href.startsWith('javascript:') || href.startsWith('tel:') || href.startsWith('mailto:')) return;
        if (link.origin !== window.location.origin) return;
        if (isNonAjaxPath(link.pathname)) return;

        e.preventDefault();
        window.loadPageSeamlessly(link.href, true);
    });

    window.addEventListener('popstate', (e) => {
        const targetUrl = (e.state && e.state.url) ? e.state.url : window.location.href;
        window.loadPageSeamlessly(targetUrl, false);
    });
}

function setupLinkPrefetch() {
    const hoverTimers = new WeakMap();

    function shouldHoverPrefetch(link) {
        if (!link) return false;
        return Boolean(link.closest('.app-sidebar, .nav-tabs, .tab-nav-btn, [data-prefetch]'));
    }

    function schedule(link, delay) {
        if (!link || !isCacheablePageUrl(link.href) || link.href === window.location.href) return;
        if (hoverTimers.has(link) || getCachedPage(link.href) || inFlightFetches.has(link.href)) return;
        const timerId = setTimeout(() => {
            hoverTimers.delete(link);
            prefetchPage(link.href);
        }, delay);
        hoverTimers.set(link, timerId);
    }

    function cancel(link) {
        if (!link) return;
        const timerId = hoverTimers.get(link);
        if (timerId) {
            clearTimeout(timerId);
            hoverTimers.delete(link);
        }
    }

    document.addEventListener('pointerover', (e) => {
        if (e.pointerType === 'touch') return;
        const link = e.target.closest('a[href]');
        if (shouldHoverPrefetch(link)) {
            schedule(link, 120);
        }
    }, { passive: true });

    document.addEventListener('pointerout', (e) => {
        const link = e.target.closest('a[href]');
        if (link && !link.contains(e.relatedTarget)) {
            cancel(link);
        }
    }, { passive: true });

    document.addEventListener('pointerdown', (e) => {
        if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
        const link = e.target.closest('a[href]');
        if (!link || link.target === '_blank' || link.hasAttribute('download')) return;
        if (link.getAttribute('data-no-ajax') === 'true' || link.getAttribute('data-native') === 'true') return;
        if (isCacheablePageUrl(link.href) && link.href !== window.location.href) {
            prefetchPage(link.href);
        }
    }, { passive: true });

    document.addEventListener('focusin', (e) => {
        const link = e.target.closest('a[href]');
        if (shouldHoverPrefetch(link)) {
            schedule(link, 250);
        }
    }, { passive: true });
}

async function prefetchPage(url) {
    if (!isCacheablePageUrl(url) || isNavigating || activePrefetches >= 2 || getCachedPage(url)) return;
    const key = new URL(url, window.location.origin).href;
    if (inFlightFetches.has(key)) return;

    activePrefetches += 1;
    const fetchPromise = fetchPageDocument(key).then(doc => {
        cachePage(key, doc);
        return doc;
    });
    inFlightFetches.set(key, fetchPromise);
    try {
        await fetchPromise;
    } catch (err) {
        // The real navigation will retry and show any error.
    } finally {
        inFlightFetches.delete(key);
        activePrefetches -= 1;
    }
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
        if (e.defaultPrevented) return;
        const form = e.target;
        if (!form || form.tagName !== 'FORM') return;

        if (form.getAttribute('data-no-ajax') === 'true') return;

        const action = form.getAttribute('action') || form.action || window.location.href;
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
            clearPageCache();

            const contentType = response.headers.get('content-type') || '';

            if (response.redirected && response.url && !contentType.includes('text/html')) {
                window.location.href = response.url;
                return;
            }

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
                if (newContent) {
                    const newMessages = newContent.querySelector('.toast-messages-container');
                    if (newMessages) newMessages.remove();
                    renderPageDocument(doc, response.url || action, { scrollTop: false });
                }

                // Update URL history without page reload
                if (response.url && response.url !== window.location.href) {
                    window.history.pushState({ url: response.url }, doc.title || '', response.url);
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
        if (table.dataset.paginatedInitialized === 'true') return;
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
    let pulseInFlight = false;

    function isUserEditing() {
        if (window._isUploadingDocs || window.isUploadingDocs) return true;
        const openModal = document.querySelector('.modal.open, .modal[style*="display: flex"], .modal[style*="display: block"]');
        if (openModal) return true;

        const active = document.activeElement;
        if (active && ['INPUT', 'TEXTAREA', 'SELECT'].includes(active.tagName)) {
            return true;
        }
        return false;
    }

    async function checkPulse() {
        if (pulseInFlight) return;
        pulseInFlight = true;

        try {
            if (document.hidden || isNavigating || isReloading || window._isUploadingDocs || window.isUploadingDocs) return;

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
                clearPageCache();

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
                if (isNavigating || isUserEditing()) {
                    pendingReload = true;
                } else {
                    seamlessContentReload();
                }
            }
        } catch (e) {
            // Quiet network recovery
        } finally {
            pulseInFlight = false;
            setTimeout(checkPulse, 10000);
        }
    }

    async function seamlessContentReload() {
        if (isReloading || isNavigating || window._isUploadingDocs || window.isUploadingDocs) return;
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
            const doc = await fetchPageDocument(targetUrl);
            if (isNavigating) {
                pendingReload = true;
                return;
            }

            const newMessages = doc.querySelector('.page-content .toast-messages-container');
            if (newMessages) newMessages.remove();
            clearPageCache();
            renderPageDocument(doc, targetUrl, { scrollTop: false });
        } catch (err) {
            // Keep the current view when a background refresh fails.
        } finally {
            isReloading = false;
            setTimeout(() => {
                if (pill) {
                    pill.style.background = '#ECFDF5';
                    pill.style.borderColor = '#A7F3D0';
                    pill.style.color = '#065F46';
                    const dot = pill.querySelector('span');
                    if (dot) dot.style.background = '#10B981';
                }
            }, 300);
        }
    }

    // Trigger reload once user finishes typing or closes modal
    document.addEventListener('focusout', () => {
        if (window._isUploadingDocs || window.isUploadingDocs) return;
        if (pendingReload && !isUserEditing()) {
            setTimeout(() => {
                if (!isUserEditing() && !window._isUploadingDocs && !window.isUploadingDocs) seamlessContentReload();
            }, 400);
        }
    });

    window.addEventListener('malkia:navigation-complete', () => {
        if (!pendingReload || isUserEditing()) return;
        setTimeout(() => {
            if (!isUserEditing() && !isNavigating) seamlessContentReload();
        }, 250);
    });

    // Check after each completed pulse so slow VPS requests never overlap.
    setTimeout(checkPulse, 10000);
})();
