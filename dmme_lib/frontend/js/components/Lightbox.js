// dmme_lib/frontend/js/components/Lightbox.js

export class Lightbox {
    constructor() {
        this.modal = document.getElementById('image-lightbox-modal');
        this.imageContent = document.getElementById('image-lightbox-content');
        this.closeBtn = document.getElementById('image-lightbox-close');

        if (!this.modal || !this.imageContent || !this.closeBtn) {
            console.error("Lightbox component could not find its required DOM elements.");
            return;
        }
        this._addEventListeners();
    }

    _addEventListeners() {
        this.closeBtn.addEventListener('click', () => this.close());
        this.modal.addEventListener('click', (e) => {
            // Close if the user clicks on the background, but not the image itself
            if (e.target === this.modal) {
                this.close();
            }
        });
    }

    open(imageUrl) {
        if (!imageUrl) return;
        this.imageContent.src = imageUrl;
        this.modal.style.display = 'block';
    }

    close() {
        this.modal.style.display = 'none';
        this.imageContent.src = ''; // Clear src to stop loading
    }
}
