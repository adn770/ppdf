// dmme_lib/frontend/js/ui.js
import { i18n } from './i18n.js';

const _gameSpinner = document.getElementById('game-spinner');
export function showGameSpinner() {
    if (_gameSpinner) _gameSpinner.style.display = 'flex';
}

export function hideGameSpinner() {
    if (_gameSpinner) _gameSpinner.style.display = 'none';
}

class ConfirmationModal {
    constructor() {
        this.modal = null;
        this.title = null;
        this.message = null;
        this.confirmBtn = null;
        this.cancelBtn = null;
        this.resolvePromise = null;
    }

    init() {
        this.modal = document.getElementById('confirmation-modal');
        this.title = document.getElementById('confirmation-title');
        this.message = document.getElementById('confirmation-message');
        this.confirmBtn = document.getElementById('confirmation-confirm-btn');
        this.cancelBtn = document.getElementById('confirmation-cancel-btn');

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

    confirm(titleKey, messageKey, replacements = {}) {
        return new Promise((resolve) => {
            this.title.textContent = i18n.t(titleKey);
            this.message.textContent = i18n.t(messageKey, replacements);
            this.resolvePromise = resolve;
            document.getElementById('modal-overlay').style.display = 'block';
            this.modal.style.display = 'flex';
        });
    }
}

// --- Global UI Instances ---
export const confirmationModal = new ConfirmationModal();
export const status = {
    _el: null,
    init() {
        this._el = document.getElementById('status-text');
    },
    setText(key, isError = false, replacements = {}) {
        if (this._el) {
            this._el.textContent = i18n.t(key, replacements);
            this._el.style.color = isError ? 'var(--danger-color)' : '#aaa';
        }
    },
    clear() {
        if (this._el) {
            this._el.textContent = i18n.t('statusBarReady');
            this._el.style.color = '#aaa';
        }
    }
};
