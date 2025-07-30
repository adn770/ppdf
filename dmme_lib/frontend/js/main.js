// dmme_lib/frontend/js/main.js

class ImportWizard {
    constructor() {
        this.modal = document.getElementById('import-wizard-modal');
        this.overlay = document.getElementById('modal-overlay');
        this.panes = this.modal.querySelectorAll('.wizard-pane');
        this.backBtn = document.getElementById('wizard-back-btn');
        this.nextBtn = document.getElementById('wizard-next-btn');
        this.finishBtn = document.getElementById('wizard-finish-btn');
        this.uploadArea = document.getElementById('wizard-upload-area');
        this.uploadInput = document.getElementById('wizard-upload-input');
        this.uploadFilename = document.getElementById('wizard-upload-filename');

        this.currentStep = 0;
        this.totalSteps = this.panes.length;
    }

    init() {
        // Main trigger
        document.getElementById('import-knowledge-btn').addEventListener('click', () => this.open());

        // Modal controls
        this.modal.querySelector('.close-btn').addEventListener('click', () => this.close());
        this.overlay.addEventListener('click', () => this.close());

        // Wizard navigation
        this.nextBtn.addEventListener('click', () => this.navigate(1));
        this.backBtn.addEventListener('click', () => this.navigate(-1));

        // File upload area
        this.uploadArea.addEventListener('click', () => this.uploadInput.click());
        this.uploadInput.addEventListener('change', (e) => this.handleFileSelect(e.target.files));

        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            this.uploadArea.addEventListener(eventName, e => this.preventDefaults(e), false);
        });
        ['dragenter', 'dragover'].forEach(eventName => {
            this.uploadArea.addEventListener(eventName, () => this.highlight(), false);
        });
        ['dragleave', 'drop'].forEach(eventName => {
            this.uploadArea.addEventListener(eventName, () => this.unhighlight(), false);
        });
        this.uploadArea.addEventListener('drop', e => this.handleFileDrop(e), false);
    }

    open() {
        this.currentStep = 0;
        this.updateView();
        this.overlay.style.display = 'block';
        this.modal.style.display = 'flex';
    }

    close() {
        this.overlay.style.display = 'none';
        this.modal.style.display = 'none';
    }

    navigate(direction) {
        this.currentStep += direction;
        this.updateView();
    }

    updateView() {
        this.panes.forEach((pane, index) => {
            pane.classList.toggle('active', index === this.currentStep);
        });

        this.backBtn.disabled = this.currentStep === 0;
        this.nextBtn.style.display = this.currentStep === this.totalSteps - 1 ? 'none' : 'block';
        this.finishBtn.style.display = this.currentStep === this.totalSteps - 1 ? 'block' : 'none';
    }

    preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    highlight() {
        this.uploadArea.classList.add('drag-over');
    }

    unhighlight() {
        this.uploadArea.classList.remove('drag-over');
    }

    handleFileDrop(e) {
        const dt = e.dataTransfer;
        const files = dt.files;
        this.handleFileSelect(files);
    }

    handleFileSelect(files) {
        if (files.length > 0) {
            this.uploadFilename.textContent = files[0].name;
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const wizard = new ImportWizard();
    wizard.init();
});
