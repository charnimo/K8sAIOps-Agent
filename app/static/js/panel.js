export class SidePanel {
    constructor() {
        this.isOpen = false;
        this.overlay = document.createElement('div');
        this.panel = document.createElement('div');
        
        // Setup overlay
        this.overlay.className = 'fixed inset-0 bg-gray-950/80 backdrop-blur-sm z-[60] hidden transition-opacity duration-300 opacity-0';
        this.overlay.addEventListener('click', () => this.close());
        
        // Setup panel
        this.panel.className = 'fixed top-0 right-0 h-screen w-full md:w-[800px] bg-gray-900 border-l border-gray-700 z-[70] shadow-2xl transform translate-x-full transition-transform duration-300 ease-in-out flex flex-col';
        
        // Header
        const header = document.createElement('div');
        header.className = 'h-16 px-6 border-b border-gray-800 flex items-center justify-between bg-gray-950';
        
        this.titleEl = document.createElement('h2');
        this.titleEl.className = 'text-lg font-bold text-white tracking-tight';
        header.appendChild(this.titleEl);
        
        const closeBtn = document.createElement('button');
        closeBtn.innerHTML = `
            <svg class="w-6 h-6 text-gray-400 hover:text-white transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
            </svg>
        `;
        closeBtn.className = 'p-1 rounded-md hover:bg-gray-800 transition-colors';
        closeBtn.addEventListener('click', () => this.close());
        header.appendChild(closeBtn);
        
        this.panel.appendChild(header);
        
        // Content container
        this.contentContainer = document.createElement('div');
        this.contentContainer.className = 'flex-1 overflow-y-auto p-6 relative';
        this.panel.appendChild(this.contentContainer);
        
        document.body.appendChild(this.overlay);
        document.body.appendChild(this.panel);
    }

    open(title, contentHtml, onMountCallback) {
        this.titleEl.textContent = title;
        this.contentContainer.innerHTML = contentHtml;
        
        // Show overlay
        this.overlay.classList.remove('hidden');
        // trigger reflow
        void this.overlay.offsetWidth;
        this.overlay.classList.remove('opacity-0');
        
        // Slide in panel
        this.panel.classList.remove('translate-x-full');
        this.isOpen = true;

        if (onMountCallback) {
            // Need a tiny timeout to ensure DOM update is complete before binding
            setTimeout(() => onMountCallback(this.contentContainer), 50);
        }
    }

    close(onUnmountCallback) {
        if (!this.isOpen) return;
        
        this.overlay.classList.add('opacity-0');
        this.panel.classList.add('translate-x-full');
        this.isOpen = false;
        
        if (this.onCloseCb) this.onCloseCb();
        if (onUnmountCallback) onUnmountCallback();
        
        setTimeout(() => {
            this.overlay.classList.add('hidden');
            this.contentContainer.innerHTML = '';
        }, 300);
    }

    onClose(cb) {
        this.onCloseCb = cb;
    }
}
