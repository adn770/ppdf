// dmme_lib/frontend/js/ui.js

class ConfirmationModal {
    constructor() {
        this.modal = document.getElementById('confirmation-modal');
        this.title = document.getElementById('confirmation-title');
        this.message = document.getElementById('confirmation-message');
        this.confirmBtn = document.getElementById('confirmation-confirm-btn');
        this.cancelBtn = document.getElementById('confirmation-cancel-btn');
        this.resolvePromise = null;

        this.confirmBtn.addEventListener('click', () => this._resolve(true));
        this.cancelBtn.addEventListener('click', () => this._resolve(false));
    }

    _resolve(value) {
        this.modal.style.display = 'none';
        document.getElementById('modal-overlay').style.display = 'none';
        if (this.resolvePromise) {
            this.resolvePromise(value);
        }
    }

    confirm(title, message) {
        return new Promise((resolve) => {
            this.title.textContent = title;
            this.message.textContent = message;
            this.resolvePromise = resolve;
            document.getElementById('modal-overlay').style.display = 'block';
            this.modal.style.display = 'flex';
        });
    }
}

// --- Global UI Instances ---
export const confirmationModal = new ConfirmationModal();
export const status = {
    _el: document.getElementById('status-text'),
    setText(message, isError = false) {
        if (this._el) {
            this._el.textContent = message;
            this._el.style.color = isError ? 'var(--danger-color)' : '#aaa';
        }
    }
};
