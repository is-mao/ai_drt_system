// DRT System - Common Utilities

// Shared HTML escape utility
function escapeHtml(text) {
    if (!text) return '';
    var div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Show Bootstrap toast notification
function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    if (!container) return;

    const bgClass = {
        'success': 'bg-success',
        'danger': 'bg-danger',
        'warning': 'bg-warning',
        'info': 'bg-primary'
    }[type] || 'bg-primary';

    const id = 'toast-' + Date.now();
    const toastEl = document.createElement('div');
    toastEl.id = id;
    toastEl.className = 'toast align-items-center text-white ' + bgClass + ' border-0';
    toastEl.setAttribute('role', 'alert');
    toastEl.innerHTML = '<div class="d-flex"><div class="toast-body"></div>' +
        '<button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button></div>';
    toastEl.querySelector('.toast-body').textContent = message;
    container.appendChild(toastEl);

    const toast = new bootstrap.Toast(toastEl, { delay: 3000 });
    toast.show();

    toastEl.addEventListener('hidden.bs.toast', () => toastEl.remove());
}

// API fetch wrapper
async function apiCall(url, options = {}) {
    const defaults = {
        headers: { 'Content-Type': 'application/json' },
    };
    const config = { ...defaults, ...options };
    if (options.body && typeof options.body === 'object' && !(options.body instanceof FormData)) {
        config.body = JSON.stringify(options.body);
    }
    if (options.body instanceof FormData) {
        delete config.headers['Content-Type'];
    }

    try {
        const response = await fetch(url, config);
        if (response.status === 401) {
            window.location.href = '/login';
            return null;
        }
        return response;
    } catch (error) {
        showToast('Network error: ' + error.message, 'danger');
        throw error;
    }
}

// Format date for display
function formatDate(dateStr) {
    if (!dateStr) return '-';
    return dateStr;
}

// Truncate text
function truncate(text, maxLen = 50) {
    if (!text) return '-';
    return text.length > maxLen ? text.substring(0, maxLen) + '...' : text;
}

// Get defect class badge
function defectClassBadge(cls) {
    if (!cls) return '<span class="badge bg-secondary">-</span>';
    const safeClass = cls.replace('&', '').replace(' ', '_');
    return `<span class="badge badge-defect-${safeClass}">${cls}</span>`;
}

// Get BU badge
function buBadge(bu) {
    if (!bu) return '-';
    const color = bu === 'CRBU' ? 'primary' : 'success';
    return `<span class="badge bg-${color}">${bu}</span>`;
}
