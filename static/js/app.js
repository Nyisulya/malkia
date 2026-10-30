// Malkia Freight & Logistics - Global Seamless Async Interactivity Engine
// Zero Full-Page Reload Architecture for Internal Actions, Modals & Tabs

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
            // Auto focus first input if present
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
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) {
                overlay.classList.remove('open');
                overlay.style.display = 'none';
                document.body.style.overflow = '';
            }
        });
    });

    // Close modal on Escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            window.closeAllModals();
        }
    });

    // 2. FLOATING TOAST NOTIFICATION SYSTEM
    window.showToast = function(message, type = 'success', duration = 5000) {
        let container = document.getElementById('globalToastContainer');
        if (!container) {
            container = document.createElement('div');
            container.id = 'globalToastContainer';
            container.className = 'global-toast-container';
            document.body.appendChild(container);
        }

        const toast = document.createElement('div');
        toast.className = `alert-toast floating-toast ${type}`;
        
        let iconHtml = '<i class="fa-solid fa-circle-check"></i>';
        if (type === 'error' || type === 'danger') {
            iconHtml = '<i class="fa-solid fa-circle-exclamation"></i>';
        } else if (type === 'warning') {
            iconHtml = '<i class="fa-solid fa-triangle-exclamation"></i>';
        } else if (type === 'info') {
            iconHtml = '<i class="fa-solid fa-circle-info"></i>';
        }

        toast.innerHTML = `
            <div style="display:flex;align-items:center;gap:0.6rem;">
                <span style="font-size:1.1rem;">${iconHtml}</span>
                <span style="font-weight:600;font-size:0.88rem;">${message}</span>
            </div>
            <button type="button" style="background:none;border:none;cursor:pointer;color:inherit;font-size:1.2rem;padding:0 0.3rem;margin-left:0.75rem;opacity:0.75;" onclick="this.closest('.alert-toast').remove()">&times;</button>
        `;

        container.appendChild(toast);

        // Slide in animation
        requestAnimationFrame(() => {
            toast.classList.add('toast-visible');
        });

        // Auto dismiss after duration
        setTimeout(() => {
            toast.classList.remove('toast-visible');
            toast.classList.add('toast-hiding');
            setTimeout(() => toast.remove(), 400);
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
        // Hide all panels in this group
        document.querySelectorAll('.' + groupClass).forEach(el => {
            el.style.display = 'none';
        });

        // Deactivate all nav buttons in this group
        document.querySelectorAll('.' + navClass).forEach(btn => {
            btn.classList.remove('active');
            if (btn.classList.contains('profile-tab-btn')) {
                btn.classList.remove('btn-primary');
                btn.classList.add('btn-outline');
            }
        });

        // Show target panel
        const activeTab = document.getElementById(tabId);
        if (activeTab) {
            activeTab.style.display = 'block';
        }

        // Activate button
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

    // Close sidebar drawer on link click on mobile
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

    // 7. GLOBAL ASYNC FORM SUBMISSION INTERCEPTOR
    setupGlobalFormInterceptor();

    // 8. ZERO-RELOAD TABLE PAGINATION ENGINE
    window.initTablePagination();
}

// Rebind helpers after dynamic DOM replacement
function rebindDynamicElements() {
    document.querySelectorAll('.progress-bar-fill[data-width]').forEach(el => {
        el.style.width = el.getAttribute('data-width') + '%';
    });

    // Close buttons on toasts
    document.querySelectorAll('.alert-toast button').forEach(btn => {
        btn.onclick = function() {
            this.closest('.alert-toast').remove();
        };
    });

    // Re-initialize table pagination after dynamic updates
    if (window.initTablePagination) {
        window.initTablePagination();
    }
}

// 8. ZERO-RELOAD UNIVERSAL TABLE PAGINATION ENGINE
window.initTablePagination = function() {
    const tables = document.querySelectorAll('table.modern-table, table.containers-table, table.data-table, table[data-paginate="true"]');
    
    tables.forEach(table => {
        const tbody = table.querySelector('tbody');
        if (!tbody) return;

        // Determine page size (default from data-page-size or 10)
        let pageSize = parseInt(table.getAttribute('data-page-size') || '10', 10);
        if (isNaN(pageSize) || pageSize < 1) pageSize = 10;

        table.dataset.paginatedInitialized = 'true';
        if (!table.dataset.currentPage) {
            table.dataset.currentPage = '1';
        }
        table.dataset.pageSize = pageSize.toString();

        // Create or locate pagination toolbar directly beneath table container
        const parentWrap = table.closest('.table-responsive') || table.parentElement;
        let toolbar = parentWrap.nextElementSibling;
        if (!toolbar || !toolbar.classList.contains('table-pagination-toolbar')) {
            toolbar = document.createElement('div');
            toolbar.className = 'table-pagination-toolbar';
            parentWrap.insertAdjacentElement('afterend', toolbar);
        }
        table._paginationToolbar = toolbar;

        // Perform initial pagination
        window.repaginateTable(table);
    });
};

window.repaginateTable = function(table, targetPage) {
    if (!table) return;
    const tbody = table.querySelector('tbody');
    if (!tbody) return;

    const toolbar = table._paginationToolbar || (table.closest('.table-responsive') || table.parentElement)?.nextElementSibling;
    if (!toolbar || !toolbar.classList.contains('table-pagination-toolbar')) return;

    // Get all content rows (exclude empty state placeholders)
    const allRows = Array.from(tbody.querySelectorAll('tr')).filter(row => {
        return !row.querySelector('td[colspan]') && row.id !== 'noResultsRow';
    });

    // Active rows are those not marked as hidden by an active filter/search
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

    // Show/hide rows for the current page
    const startIndex = (currentPage - 1) * pageSize;
    const endIndex = Math.min(startIndex + pageSize, totalItems);

    activeRows.forEach((row, idx) => {
        if (idx >= startIndex && idx < endIndex) {
            row.style.display = '';
        } else {
            row.style.display = 'none';
        }
    });

    // Toggle empty row visibility
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

    // Build pagination controls HTML
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

    // Attach listeners
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

// Global AJAX Form Interceptor: prevents full-page reloads on all internal action forms
function setupGlobalFormInterceptor() {
    let lastSubmitter = null;

    // Track which submit button was clicked (to get name/value e.g. decision="APPROVE")
    document.addEventListener('click', (e) => {
        const btn = e.target.closest('button[type="submit"], input[type="submit"]');
        if (btn) {
            lastSubmitter = btn;
        }
    }, true);

    document.addEventListener('submit', async (e) => {
        const form = e.target;
        if (!form || form.tagName !== 'FORM') return;

        // Check if form should bypass AJAX (e.g. login, logout, explicit data-no-ajax)
        if (form.getAttribute('data-no-ajax') === 'true') return;
        
        const method = (form.getAttribute('method') || 'GET').toUpperCase();
        if (method !== 'POST') return; // Let GET search forms work or handle separately

        const action = form.getAttribute('action') || window.location.href;
        if (action.includes('/login/') || action.includes('/logout/')) return;

        // Intercept form submission!
        e.preventDefault();

        // Get submit button and show loading state
        const submitBtn = lastSubmitter || form.querySelector('button[type="submit"]');
        let originalBtnHtml = '';
        if (submitBtn) {
            originalBtnHtml = submitBtn.innerHTML;
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Processing...';
        }

        try {
            const formData = new FormData(form);

            // Include the clicked button's name & value if applicable (e.g. name="decision" value="APPROVE")
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

            // Check if response is redirected to another page (e.g., job creation redirecting to job detail)
            if (response.redirected && response.url && !response.url.endsWith(window.location.pathname)) {
                // If it redirected to a completely different URL, navigate cleanly
                window.location.href = response.url;
                return;
            }

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
                // HTML Response from Django view (rendered page after redirect/render)
                const responseHtml = await response.text();
                const parser = new DOMParser();
                const doc = parser.parseFromString(responseHtml, 'text/html');

                // 1. Extract Flash Messages and show them as floating toasts
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

                // Default success toast if no message container in response
                if (!foundMessage && response.ok) {
                    window.showToast('Information updated successfully!', 'success');
                }

                // 2. Close any open modals
                window.closeAllModals();

                // 3. Seamlessly update .page-content with new state without page refresh
                const newContent = doc.querySelector('.page-content');
                const currentContent = document.querySelector('.page-content');
                if (newContent && currentContent) {
                    // Remove old messages from newly inserted content to avoid duplication (since toasts are showing)
                    const newMessages = newContent.querySelector('.toast-messages-container');
                    if (newMessages) newMessages.remove();

                    currentContent.innerHTML = newContent.innerHTML;
                }

                // 4. Update sidebar badges from response HTML
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

                // 5. Rebind dynamic elements (progress bars, tabs, listeners)
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
        }
    });
}
