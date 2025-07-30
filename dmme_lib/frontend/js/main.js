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
        this.selectedFile = null;
        this.knowledgeBaseName = '';
        this.reviewImages = [];
        this.currentReviewIndex = 0;

        this.reviewUI = document.getElementById('image-review-ui');
        this.reviewLoading = document.getElementById('image-review-loading');
        this.reviewImage = document.getElementById('review-image');
        this.reviewCounter = document.getElementById('image-review-counter');
        this.imgDesc = document.getElementById('image-description');
        this.imgClass = document.getElementById('image-classification');
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

        document.getElementById('image-prev-btn').addEventListener('click', () => this.navigateReviewImage(-1));
        document.getElementById('image-next-btn').addEventListener('click', () => this.navigateReviewImage(1));
        document.getElementById('save-image-changes-btn').addEventListener('click', () => this.saveImageChanges());
    }

    open() {
        this.currentStep = 0;
        this.selectedFile = null;
        this.knowledgeBaseName = '';
        this.reviewImages = [];
        this.currentReviewIndex = 0;
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
        this.currentStep = Math.max(0, Math.min(this.currentStep + direction, this.totalSteps - 1));
        this.updateView();
    }

    updateView() {
        this.panes.forEach((pane, index) => {
            pane.classList.toggle('active', index === this.currentStep);
        });
        this.backBtn.disabled = this.currentStep === 0;
        this.nextBtn.style.display = this.currentStep >= this.totalSteps - 1 ? 'none' : 'block';
        this.finishBtn.style.display = this.currentStep >= 1 ? 'block' : 'none';
        
        if (this.currentStep < 2) {
             this.finishBtn.textContent = 'Next';
        } else {
             this.finishBtn.textContent = 'Finish Ingestion';
        }

        document.getElementById('wizard-title').textContent = this.knowledgeBaseName ?
            `Importing: ${this.knowledgeBaseName}` : 'Import Knowledge Wizard';
    }

    preventDefaults(e) { e.preventDefault(); e.stopPropagation(); }
    highlight() { this.uploadArea.classList.add('drag-over'); }
    unhighlight() { this.uploadArea.classList.remove('drag-over'); }

    handleFileDrop(e) { this.handleFileSelect(e.dataTransfer.files); }

    handleFileSelect(files) {
        if (files.length > 0) {
            this.selectedFile = files[0];
            this.uploadFilename.textContent = this.selectedFile.name;
        }
    }

    async handleFinish() {
        if (this.currentStep === 0) { // On Upload page
            this.navigate(1);
        } else if (this.currentStep === 1) { // On Metadata page
            const kbNameInput = document.getElementById('kb-name');
            this.knowledgeBaseName = kbNameInput.value.trim();
            if (!this.selectedFile) { alert("Please select a file."); this.navigate(-1); return; }
            if (!this.knowledgeBaseName) { alert("Please provide a name."); return; }
            
            await this.ingestText();
            
            if (this.selectedFile.name.toLowerCase().endsWith('.pdf')) {
                await this.startImageExtraction();
                await this.loadImagesForReview();
            } else {
                alert("Knowledge base created successfully.");
                this.close();
            }
        } else if (this.currentStep === 2) { // On Review page
            await this.finalizeImageIngestion();
        }
    }

    createFormData(includeFile = true) {
        const kbDesc = document.getElementById('kb-desc').value.trim();
        const kbType = document.querySelector('input[name="kb-type"]:checked').value;
        const formData = new FormData();
        if (includeFile) formData.append('file', this.selectedFile);
        formData.append('metadata', JSON.stringify({
            kb_name: this.knowledgeBaseName,
            kb_type: kbType,
            description: kbDesc,
        }));
        return formData;
    }
    
    setLoadingState(isLoading, text = 'Loading...') {
        this.finishBtn.disabled = isLoading;
        this.finishBtn.textContent = isLoading ? text : 'Finish';
        this.backBtn.disabled = isLoading;
    }

    async ingestText() {
        const formData = this.createFormData();
        this.setLoadingState(true, 'Ingesting text...');
        try {
            const response = await fetch('/api/knowledge/import-text', { method: 'POST', body: formData });
            if (!response.ok) throw new Error((await response.json()).error);
        } catch (error) {
            alert(`Error ingesting text: ${error.message}`);
            this.setLoadingState(false, 'Finish');
            throw error;
        }
        this.setLoadingState(false, 'Finish');
    }

    async startImageExtraction() {
        const formData = new FormData();
        formData.append('file', this.selectedFile);
        formData.append('kb_name', this.knowledgeBaseName);
        this.panes[2].querySelector('#image-review-loading').style.display = 'flex';
        this.panes[2].querySelector('#image-review-ui').style.display = 'none';
        this.navigate(1); // Move to review pane to show loading
        this.setLoadingState(true, 'Extracting images...');
        try {
            const response = await fetch('/api/knowledge/start-image-extraction', { method: 'POST', body: formData });
            if (!response.ok) throw new Error((await response.json()).error);
        } catch (error) {
            alert(`Error starting image extraction: ${error.message}`);
            this.setLoadingState(false, 'Finish');
            throw error;
        }
    }

    async loadImagesForReview() {
        try {
            const response = await fetch(`/api/knowledge/review-images/${this.knowledgeBaseName}`);
            this.reviewImages = await response.json();
            if (this.reviewImages.length > 0) {
                this.currentReviewIndex = 0;
                this.displayReviewImage();
                this.reviewLoading.style.display = 'none';
                this.reviewUI.style.display = 'flex';
                this.setLoadingState(false, 'Finish Ingestion');
            } else {
                alert("Text ingested successfully (no images found to review).");
                this.close();
            }
        } catch (error) {
            alert(`Error loading images for review: ${error.message}`);
            this.close();
        }
    }

    displayReviewImage() {
        const current = this.reviewImages[this.currentReviewIndex];
        this.reviewImage.src = current.url;
        this.reviewCounter.textContent = `${this.currentReviewIndex + 1} / ${this.reviewImages.length}`;
        this.imgDesc.value = current.metadata.description;
        this.imgClass.value = current.metadata.classification;
        document.getElementById('image-save-status').textContent = '';
        document.getElementById('image-prev-btn').disabled = this.currentReviewIndex === 0;
        document.getElementById('image-next-btn').disabled = this.currentReviewIndex === this.reviewImages.length - 1;
    }

    navigateReviewImage(dir) {
        const newIndex = this.currentReviewIndex + dir;
        if (newIndex >= 0 && newIndex < this.reviewImages.length) {
            this.currentReviewIndex = newIndex;
            this.displayReviewImage();
        }
    }

    async saveImageChanges() {
        const current = this.reviewImages[this.currentReviewIndex];
        const statusEl = document.getElementById('image-save-status');
        const payload = {
            description: this.imgDesc.value.trim(),
            classification: this.imgClass.value,
        };
        try {
            statusEl.textContent = 'Saving...';
            const response = await fetch(`/api/knowledge/review-images/${this.knowledgeBaseName}/${current.filename}`, {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload)
            });
            if (!response.ok) throw new Error((await response.json()).error);
            current.metadata.description = payload.description;
            current.metadata.classification = payload.classification;
            statusEl.textContent = 'Saved!';
            setTimeout(() => statusEl.textContent = '', 2000);
        } catch(error) {
            statusEl.textContent = `Error: ${error.message}`;
        }
    }
    
    async finalizeImageIngestion() {
        this.setLoadingState(true, 'Finalizing...');
        try {
            const response = await fetch('/api/knowledge/ingest-images', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ kb_name: this.knowledgeBaseName })
            });
            if (!response.ok) throw new Error((await response.json()).error);
            alert("Knowledge base with images created successfully!");
            this.close();
        } catch (error) {
            alert(`Error finalizing ingestion: ${error.message}`);
        } finally {
            this.setLoadingState(false, 'Finish Ingestion');
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const wizard = new ImportWizard();
    wizard.init();
});
