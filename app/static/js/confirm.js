let modalRoot = null;

function ensureModal() {
    if (modalRoot) return modalRoot;

    modalRoot = document.createElement('div');
    modalRoot.className = 'fixed inset-0 z-[120] hidden items-center justify-center p-4';
    modalRoot.innerHTML = `
        <div data-confirm-backdrop class="absolute inset-0 bg-gray-950/80 backdrop-blur-sm opacity-0 transition-opacity duration-200"></div>
        <div data-confirm-dialog class="relative w-full max-w-md rounded-2xl border border-gray-700 bg-gradient-to-br from-gray-900 via-gray-900 to-gray-800 shadow-2xl shadow-black/40 transform translate-y-4 opacity-0 transition-all duration-200">
            <div class="p-6 border-b border-gray-800">
                <div class="inline-flex items-center justify-center w-10 h-10 rounded-xl bg-amber-900/40 border border-amber-700/40 mb-3">
                    <svg class="w-5 h-5 text-amber-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01M10.29 3.86l-7.2 12.46A2 2 0 004.82 19h14.36a2 2 0 001.73-2.68l-7.2-12.46a2 2 0 00-3.46 0z"/>
                    </svg>
                </div>
                <h3 data-confirm-title class="text-lg font-bold text-white tracking-tight">Please Confirm</h3>
                <p data-confirm-message class="mt-2 text-sm text-gray-300">Are you sure you want to continue?</p>
            </div>
            <div class="p-4 flex items-center justify-end gap-3">
                <button data-confirm-cancel type="button" class="px-4 py-2 rounded-lg border border-gray-700 bg-gray-800 text-gray-200 hover:bg-gray-700 transition-colors text-sm font-medium">Cancel</button>
                <button data-confirm-ok type="button" class="px-4 py-2 rounded-lg border border-rose-700/50 bg-rose-900/40 text-rose-200 hover:bg-rose-800/50 transition-colors text-sm font-semibold">Confirm</button>
            </div>
        </div>
    `;

    document.body.appendChild(modalRoot);
    return modalRoot;
}

export function showConfirmModal(options = {}) {
    const {
        title = 'Please Confirm',
        message = 'Are you sure you want to continue?',
        confirmText = 'Confirm',
        cancelText = 'Cancel',
        intent = 'danger',
        allowBackdropClose = true,
    } = options;

    const root = ensureModal();
    const backdrop = root.querySelector('[data-confirm-backdrop]');
    const dialog = root.querySelector('[data-confirm-dialog]');
    const titleEl = root.querySelector('[data-confirm-title]');
    const messageEl = root.querySelector('[data-confirm-message]');
    const cancelBtn = root.querySelector('[data-confirm-cancel]');
    const okBtn = root.querySelector('[data-confirm-ok]');

    titleEl.textContent = title;
    messageEl.textContent = message;
    cancelBtn.textContent = cancelText;
    okBtn.textContent = confirmText;

    okBtn.className = 'px-4 py-2 rounded-lg transition-colors text-sm font-semibold';
    if (intent === 'warning') {
        okBtn.classList.add('border', 'border-amber-700/50', 'bg-amber-900/40', 'text-amber-200', 'hover:bg-amber-800/50');
    } else if (intent === 'success') {
        okBtn.classList.add('border', 'border-emerald-700/50', 'bg-emerald-900/40', 'text-emerald-200', 'hover:bg-emerald-800/50');
    } else {
        okBtn.classList.add('border', 'border-rose-700/50', 'bg-rose-900/40', 'text-rose-200', 'hover:bg-rose-800/50');
    }

    return new Promise((resolve) => {
        let done = false;

        const close = (result) => {
            if (done) return;
            done = true;
            backdrop.classList.remove('opacity-100');
            dialog.classList.remove('opacity-100', 'translate-y-0');
            dialog.classList.add('opacity-0', 'translate-y-4');

            window.removeEventListener('keydown', onKeydown);
            backdrop.removeEventListener('click', onBackdrop);
            cancelBtn.removeEventListener('click', onCancel);
            okBtn.removeEventListener('click', onConfirm);

            setTimeout(() => {
                root.classList.add('hidden');
                root.classList.remove('flex');
                resolve(result);
            }, 180);
        };

        const onCancel = () => close(false);
        const onConfirm = () => close(true);
        const onBackdrop = () => {
            if (allowBackdropClose) close(false);
        };
        const onKeydown = (e) => {
            if (e.key === 'Escape') close(false);
            if (e.key === 'Enter') close(true);
        };

        backdrop.addEventListener('click', onBackdrop);
        cancelBtn.addEventListener('click', onCancel);
        okBtn.addEventListener('click', onConfirm);
        window.addEventListener('keydown', onKeydown);

        root.classList.remove('hidden');
        root.classList.add('flex');

        requestAnimationFrame(() => {
            backdrop.classList.add('opacity-100');
            dialog.classList.remove('opacity-0', 'translate-y-4');
            dialog.classList.add('opacity-100', 'translate-y-0');
        });
    });
}
