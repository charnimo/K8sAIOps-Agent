window.showToast = function(message, type = "success") {
    // Remove existing toast if any
    const existing = document.getElementById("custom-toast");
    if (existing) existing.remove();

    const toast = document.createElement("div");
    toast.id = "custom-toast";
    
    // Base classes
    let classes = "fixed top-5 left-1/2 transform -translate-x-1/2 px-6 py-3 rounded-lg shadow-2xl transition-all duration-300 z-50 flex items-center space-x-3 text-white font-medium ";
    
    // Type specific styling
    if (type === "success") {
        classes += "bg-emerald-600 border-b-4 border-emerald-800";
    } else if (type === "error") {
        classes += "bg-rose-600 border-b-4 border-rose-800";
    } else if (type === "warning") {
        classes += "bg-amber-500 border-b-4 border-amber-700";
    } else {
        classes += "bg-indigo-600 border-b-4 border-indigo-800";
    }

    toast.className = classes;
    
    // Icons based on type
    let icon = "";
    if (type === "success") icon = `<svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>`;
    else if (type === "error") icon = `<svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>`;
    else if (type === "warning") icon = `<svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>`;
    else icon = `<svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>`;

    toast.innerHTML = `
        ${icon}
        <span>${message}</span>
    `;

    document.body.appendChild(toast);

    // Initial animation state
    toast.style.opacity = "0";
    toast.style.transform = "translate(-50%, -20px)";
    
    // Animate in
    requestAnimationFrame(() => {
        toast.style.opacity = "1";
        toast.style.transform = "translate(-50%, 0)";
    });

    // Auto remove after 3s
    setTimeout(() => {
        toast.style.opacity = "0";
        toast.style.transform = "translate(-50%, -20px)";
        setTimeout(() => toast.remove(), 300);
    }, 3000);
};
