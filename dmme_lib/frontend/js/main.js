// --- dmme_lib/frontend/js/main.js ---
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
        this.selectedFile = null;
    }

    init() {
        document.getElementById('import-knowledge-btn').addEventListener('click', () => this.open());
        this.modal.querySelector('.close-btn').addEventListener('click', () => this.close());
        this.overlay.addEventListener('click', () => this.close());
        this.nextBtn.addEventListener('click', () => this.navigate(1));
        this.backBtn.addEventListener('click', () => this.navigate(-1));
        this.finishBtn.addEventListener('click', () => this.handleFinish());

        this.uploadArea.addEventListener('click', () => this.uploadInput.click());
        this.uploadInput.addEventListener('change', (e) => this.handleFileSelect(e.target.files));

        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eName => {
            this.uploadArea.addEventListener(eName, e => this.preventDefaults(e), false);
        });
        ['dragenter', 'dragover'].forEach(eName => {
            this.uploadArea.addEventListener(eName, () => this.highlight(), false);
        });
        ['dragleave', 'drop'].forEach(eName => {
            this.uploadArea.addEventListener(eName, () => this.unhighlight(), false);
        });
        this.uploadArea.addEventListener('drop', e => this.handleFileDrop(e), false);
    }

    open() {
        // Reset form state
        this.currentStep = 0;
        this.selectedFile = null;
        this.uploadFilename.textContent = '';
        this.uploadInput.value = '';
        document.getElementById('kb-name').value = '';
        document.getElementById('kb-desc').value = '';
        
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
        this.nextBtn.style.display = this.currentStep >= this.totalSteps - 1 ? 'none' : 'block';
        this.finishBtn.style.display = this.currentStep >= this.totalSteps - 1 ? 'block' : 'none';
    }

    preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    highlight() { this.uploadArea.classList.add('drag-over'); }
    unhighlight() { this.uploadArea.classList.remove('drag-over'); }

    handleFileDrop(e) {
        const dt = e.dataTransfer;
        this.handleFileSelect(dt.files);
    }

    handleFileSelect(files) {
        if (files.length > 0) {
            this.selectedFile = files[0];
            this.uploadFilename.textContent = this.selectedFile.name;
        }
    }

    async handleFinish() {
        const kbNameInput = document.getElementById('kb-name');
        const kbName = kbNameInput.value.trim();
        const kbType = document.querySelector('input[name="kb-type"]:checked').value;
        const kbDesc = document.getElementById('kb-desc').value.trim();

        if (!this.selectedFile) {
            alert("Please select a file to import.");
            return;
        }
        if (!kbName) {
            alert("Please provide a name for the knowledge base.");
            this.currentStep = 1; // Go to metadata step
            this.updateView();
            kbNameInput.focus();
            return;
        }

        const formData = new FormData();
        formData.append('file', this.selectedFile);
        formData.append('metadata', JSON.stringify({
            kb_name: kbName,
            kb_type: kbType,
            description: kbDesc,
        }));

        this.finishBtn.disabled = true;
        this.finishBtn.textContent = 'Ingesting...';

        try {
            const response = await fetch('/api/knowledge/import', {
                method: 'POST',
                body: formData,
            });

            const result = await response.json();
            if (!response.ok) {
                throw new Error(result.error || 'An unknown error occurred.');
            }

            alert(`Success: ${result.message}`);
            this.close();

        } catch (error) {
            alert(`Error: ${error.message}`);
        } finally {
            this.finishBtn.disabled = false;
            this.finishBtn.textContent = 'Finish';
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const wizard = new ImportWizard();
    wizard.init();
});
