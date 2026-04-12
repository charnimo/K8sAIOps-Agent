export class AuthManager {
    constructor() {
        this.token = localStorage.getItem("jwt_token");
        this.userDisplay = document.getElementById('activeUserDisplay');
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

        if (this.logoutBtn) {
            this.logoutBtn.addEventListener('click', () => this.logout());
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
        window.location.href = "/static/login.html";
    }

    getToken() {
        return this.token;
    }
}
