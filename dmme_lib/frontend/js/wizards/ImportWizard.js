// dmme_lib/frontend/js/wizards/ImportWizard.js
import { apiCall } from './ApiHelper.js';

export class ImportWizard {
    constructor() {
        this.currentStep = 0;
        this.totalSteps = 2;
        this.selectedFile = null;
        this.knowledgeBaseName = '';
        this.reviewImages = [];
        this.currentReviewIndex = 0;
    }

    init() {
        // This method now does nothing, as the open button is handled by main.js
    }
    
    _addEventListeners() {
        this.modal.querySelector('.close-btn').addEventListener('click', () => this.close());
        this.overlay.addEventListener('click', (e) => {
            if (e.target === this.overlay) this.close()
        });
        this.nextBtn.addEventListener('click', () => this.handleNext());
        this.backBtn.addEventListener('click', () => this.navigate(-1));
        this.uploadArea.addEventListener('click', () => this.uploadInput.click());
        this.uploadInput.addEventListener('change', 
            (e) => this.handleFileSelect(e.target.files)
        );
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
        document.getElementById('image-prev-btn').addEventListener('click', 
            () => this.navigateReviewImage(-1)
        );
        document.getElementById('image-next-btn').addEventListener('click', 
            () => this.navigateReviewImage(1)
        );
        document.getElementById('save-image-changes-btn').addEventListener('click', 
            () => this.saveImageChanges()
        );
    }

    open() {
        // Query for elements just-in-time when the modal is opened
        this.modal = document.getElementById('import-wizard-modal');
        this.overlay = document.getElementById('modal-overlay');
        this.panes = this.modal.querySelectorAll('.wizard-pane');
        this.backBtn = document.getElementById('import-wizard-back-btn');
        this.nextBtn = document.getElementById('import-wizard-next-btn');
        this.uploadArea = document.getElementById('wizard-upload-area');
        this.uploadInput = document.getElementById('wizard-upload-input');
        this.uploadFilename = document.getElementById('wizard-upload-filename');
        this.reviewUI = document.getElementById('image-review-ui');
        this.reviewLoading = document.getElementById('image-review-loading');
        this.reviewImage = document.getElementById('review-image');
        this.reviewCounter = document.getElementById('image-review-counter');
        this.imgDesc = document.getElementById('image-description');
        this.imgClass = document.getElementById('image-classification');
        
        this._addEventListeners();
        this.resetState();
        this.updateView();
        this.overlay.style.display = 'block';
        this.modal.style.display = 'flex';
    }

    close() {
        if (this.nextBtn && this.nextBtn.disabled) return;
        this.overlay.style.display = 'none';
        this.modal.style.display = 'none';
    }

    resetState() {
        this.currentStep = 0;
        this.selectedFile = null;
        this.knowledgeBaseName = '';
        this.reviewImages = [];
        this.currentReviewIndex = 0;
        this.uploadFilename.textContent = '';
        this.uploadInput.value = '';
        document.getElementById('kb-name').value = '';
        document.getElementById('kb-desc').value = '';
        this.unhighlight();
    }

    navigate(direction) {
        const newStep = this.currentStep + direction;
        this.currentStep = Math.max(0, Math.min(newStep, this.totalSteps));
        this.updateView();
    }

    updateView() {
        this.panes.forEach((pane, index) => {
            pane.classList.toggle('active', index === this.currentStep);
        });
        this.backBtn.disabled = (this.currentStep === 0 || this.nextBtn.disabled);
        
        const isPdf = this.selectedFile && 
            this.selectedFile.name.toLowerCase().endsWith('.pdf');
        
        if (this.currentStep === 0) {
            this.nextBtn.textContent = 'Next';
        } else if (this.currentStep === 1) {
            this.nextBtn.textContent = isPdf ? 'Extract Images' : 'Finish Ingestion';
        } else if (this.currentStep === 2) {
            this.nextBtn.textContent = 'Finalize Image Ingestion';
        }

        const title = document.getElementById('import-wizard-title');
        title.textContent = this.knowledgeBaseName 
            ? `Importing: ${this.knowledgeBaseName}` 
            : 'Import Knowledge Wizard';
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
        this.handleFileSelect(e.dataTransfer.files);
    }

    handleFileSelect(files) {
        if (files.length > 0) {
            this.selectedFile = files[0];
            this.uploadFilename.textContent = this.selectedFile.name;
            this.updateView();
        }
    }

    async handleNext() {
        if (this.currentStep === 0) {
            const kbNameInput = document.getElementById('kb-name');
            this.knowledgeBaseName = kbNameInput.value.trim();
            if (!this.selectedFile) {
                alert("Please select a file.");
                return;
            }
            if (!this.knowledgeBaseName) {
                alert("Please provide a name.");
                return;
            }
            this.navigate(1);
        } else if (this.currentStep === 1) {
            await this.ingestText();
            const isPdf = this.selectedFile.name.toLowerCase().endsWith('.pdf');
            if (isPdf) {
                this.navigate(1);
                await this.startImageExtraction();
                await this.loadImagesForReview();
            } else {
                alert("Knowledge base created successfully.");
                this.close();
            }
        } else if (this.currentStep === 2) {
            await this.finalizeImageIngestion();
        }
    }
    
    setLoadingState(isLoading, text = 'Loading...') {
        this.nextBtn.disabled = isLoading;
        if (isLoading) {
            this.nextBtn.textContent = text;
        }
        this.backBtn.disabled = isLoading;
        this.modal.querySelector('.close-btn').style.cursor = 
            isLoading ? 'not-allowed' : 'pointer';
    }

    async ingestText() {
        const formData = new FormData();
        const kbDesc = document.getElementById('kb-desc').value.trim();
        const kbType = document.querySelector('input[name="kb-type"]:checked').value;
        formData.append('file', this.selectedFile);
        formData.append('metadata', JSON.stringify({
            kb_name: this.knowledgeBaseName,
            kb_type: kbType,
            description: kbDesc,
        }));

        this.setLoadingState(true, 'Ingesting text...');
        try {
            await apiCall('/api/knowledge/import-text', {
                method: 'POST',
                body: formData
            });
        } catch (error) {
            this.setLoadingState(false);
            this.updateView();
            throw error;
        }
        this.setLoadingState(false);
        this.updateView();
    }

    async startImageExtraction() {
        const formData = new FormData();
        formData.append('file', this.selectedFile);
        formData.append('kb_name', this.knowledgeBaseName);
        this.reviewLoading.style.display = 'flex';
        this.reviewUI.style.display = 'none';
        this.setLoadingState(true, 'Extracting images...');
        try {
            await apiCall('/api/knowledge/start-image-extraction', {
                method: 'POST',
                body: formData
            });
        } catch (error) {
            this.setLoadingState(false);
            this.updateView();
            throw error;
        }
    }

    async loadImagesForReview() {
        try {
            const url = `/api/knowledge/review-images/${this.knowledgeBaseName}`;
            this.reviewImages = await apiCall(url);
            if (this.reviewImages.length > 0) {
                this.currentReviewIndex = 0;
                this.displayReviewImage();
                this.reviewLoading.style.display = 'none';
                this.reviewUI.style.display = 'flex';
                this.setLoadingState(false);
                this.updateView();
            } else {
                alert("Text ingested successfully (no images found to review).");
                this.close();
            }
        } catch (error) {
            this.close();
        }
    }

    displayReviewImage() {
        const current = this.reviewImages[this.currentReviewIndex];
        this.reviewImage.src = `${current.url}?t=${new Date().getTime()}`;
        this.reviewCounter.textContent = 
            `${this.currentReviewIndex + 1} / ${this.reviewImages.length}`;
        this.imgDesc.value = current.metadata.description;
        this.imgClass.value = current.metadata.classification;
        document.getElementById('image-save-status').textContent = '';
        document.getElementById('image-prev-btn').disabled = this.currentReviewIndex === 0;
        const nextBtn = document.getElementById('image-next-btn');
        nextBtn.disabled = this.currentReviewIndex === this.reviewImages.length - 1;
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
            const url = 
                `/api/knowledge/review-images/${this.knowledgeBaseName}/${current.filename}`;
            await apiCall(url, {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload)
            });
            current.metadata.description = payload.description;
            current.metadata.classification = payload.classification;
            statusEl.textContent = 'Saved!';
            setTimeout(() => statusEl.textContent = '', 2000);
        } catch(error) {
            statusEl.textContent = `Error!`;
        }
    }
    
    async finalizeImageIngestion() {
        this.setLoadingState(true, 'Finalizing...');
        try {
            await apiCall('/api/knowledge/ingest-images', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ kb_name: this.knowledgeBaseName })
            });
            alert("Knowledge base with images created successfully!");
            this.close();
        } catch (error) {
            // Error is handled by apiCall helper
        } finally {
            this.setLoadingState(false);
            this.updateView();
        }
    }
}
