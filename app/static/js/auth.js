export class AuthManager {
    constructor() {
        this.token = localStorage.getItem("jwt_token");
        this.userDisplay = document.getElementById('activeUserDisplay');
        this.userAvatar = document.getElementById('activeUserAvatar');
        this.userAvatarFallback = document.getElementById('activeUserAvatarFallback');
        this.logoutBtn = document.getElementById('logoutBtn');
        
        this.init();
    }

    init() {
        if (!this.token) {
            window.location.href = "/static/login.html";
            return;
        }
        
        const claims = this.parseJwt(this.token);
        if (claims && claims.sub && this.userDisplay) {
            this.userDisplay.innerText = claims.sub;
        }

        this.loadProfile();

        if (this.logoutBtn) {
            this.logoutBtn.addEventListener('click', () => this.logout());
        }
    }

    async loadProfile() {
        if (!this.token) return;
        try {
            const res = await fetch('/auth/me', {
                headers: { 'Authorization': `Bearer ${this.token}` }
            });
            if (!res.ok) return;
            const profile = await res.json();

            if (this.userDisplay && profile.username) {
                this.userDisplay.innerText = profile.username;
            }

            if (this.userAvatar && profile.profile_picture) {
                this.userAvatar.src = profile.profile_picture;
                this.userAvatar.classList.remove('hidden');
                if (this.userAvatarFallback) this.userAvatarFallback.classList.add('hidden');
                this.userAvatar.onerror = () => {
                    this.userAvatar.classList.add('hidden');
                    if (this.userAvatarFallback) this.userAvatarFallback.classList.remove('hidden');
                };
            }
        } catch (e) {
            // Keep fallback avatar when profile fetch fails.
        }
    }

    parseJwt(token) {
        try { 
            return JSON.parse(atob(token.split('.')[1])); 
        } catch (e) { 
            return null; 
        }
    }

    logout() {
        localStorage.removeItem("jwt_token");
        localStorage.removeItem("active_namespace");
        window.location.href = "/static/login.html";
    }

    getToken() {
        return this.token;
    }
}
