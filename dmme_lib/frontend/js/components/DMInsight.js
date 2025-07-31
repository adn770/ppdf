// dmme_lib/frontend/js/components/DMInsight.js

export class DMInsight {
    constructor() {
        this.modal = document.getElementById('dm-insight-modal');
        this.overlay = document.getElementById('modal-overlay');
        this.contentEl = document.getElementById('dm-insight-content');
        this.closeBtn = this.modal.querySelector('.close-btn');

        this._addEventListeners();
    }

    _addEventListeners() {
        this.closeBtn.addEventListener('click', () => this.close());
        this.overlay.addEventListener('click', (e) => {
            if (e.target === this.overlay && this.modal.style.display === 'flex') {
                this.close();
            }
        });
    }

    open(context) {
        this.contentEl.textContent = context;
        this.overlay.style.display = 'block';
        this.modal.style.display = 'flex';
    }

    close() {
        // Only hide the overlay if no other modals are active
        const isAnotherModalActive = document.querySelector('.modal[style*="display: flex"]:not(#dm-insight-modal)');
        if (!isAnotherModalActive) {
            this.overlay.style.display = 'none';
        }
        this.modal.style.display = 'none';
    }
}
