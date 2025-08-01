// dmme_lib/frontend/js/wizards/ImportWizard.js
import { apiCall } from './ApiHelper.js';
import { status } from '../ui.js';

export class ImportWizard {
    constructor() {
        this.currentStep = 0;
        this.totalSteps = 3; // 0:Details, 1:Processing, 2:Review
        this.selectedFile = null;
        this.serverTempFilePath = null;
        this.knowledgeBaseName = '';
        this.reviewImages = [];
        this.currentReviewIndex = 0;
        this.uploadDefaultText =
            'Drag & Drop a PDF or Markdown file here, or click to select';
        this.reviewListenersAttached = false;
        this.progressLog = null;
        this.isProcessing = false;

        // --- DOM Element Querying & Listener Setup (Moved from open()) ---
        // This ensures event listeners are only attached once for the lifetime
        // of the component, preventing the double-dialog bug.
        this.modal = document.getElementById('import-wizard-modal');
        this.overlay = document.getElementById('modal-overlay');
        this.panes = this.modal.querySelectorAll('.wizard-pane');
        this.backBtn = document.getElementById('import-wizard-back-btn');
        this.nextBtn = document.getElementById('import-wizard-next-btn');
        this.uploadArea = document.getElementById('wizard-upload-area');
        this.uploadInput = document.getElementById('wizard-upload-input');
        this.uploadText = document.getElementById('wizard-upload-text');
        this.reviewImage = document.getElementById('review-image');
        this.reviewCounter = document.getElementById('image-review-counter');
        this.imgDesc = document.getElementById('image-description');
        this.spinner = this.modal.querySelector('.spinner');

        this._addEventListeners();
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
    }

    _initReviewListeners() {
        if (this.reviewListenersAttached) return;
        this.prevImgBtn = document.getElementById('image-prev-btn');
        this.nextImgBtn = document.getElementById('image-next-btn');
        this.saveImgBtn = document.getElementById('save-image-changes-btn');
        this.discardImgBtn = document.getElementById('discard-image-btn');

        this.prevImgBtn.addEventListener('click', () => this.navigateReviewImage(-1));
        this.nextImgBtn.addEventListener('click', () => this.navigateReviewImage(1));
        this.saveImgBtn.addEventListener('click', () => this.saveImageChanges());
        this.discardImgBtn.addEventListener('click', () => this.discardCurrentImage());

        this.reviewListenersAttached = true;
    }

    open() {
        this.resetState();
        this.updateView();
        this.overlay.style.display = 'block';
        this.modal.style.display = 'flex';
    }

    close() {
        if (this.isProcessing) return;
        this.overlay.style.display = 'none';
        this.modal.style.display = 'none';
    }

    resetState() {
        this.currentStep = 0;
        this.selectedFile = null;
        this.serverTempFilePath = null;
        this.knowledgeBaseName = '';
        this.reviewImages = [];
        this.currentReviewIndex = 0;
        this.uploadText.textContent = this.uploadDefaultText;
        this.uploadText.classList.remove('has-file');
        this.uploadInput.value = '';
        document.getElementById('kb-name').value = '';
        document.getElementById('kb-desc').value = '';
        this.unhighlight();
        this.progressLog = null;
        this.isProcessing = false;
        this.updateView();
        // Reset buttons are handled in updateView
    }

    navigate(direction) {
        const newStep = this.currentStep + direction;
        this.currentStep = Math.max(0, Math.min(newStep, this.totalSteps - 1));
        this.updateView();
    }

    updateView() {
        this.panes.forEach((pane, index) => {
            pane.classList.toggle('active', index === this.currentStep);
        });
        const finalizeContainer = this.modal.querySelector('.modal-footer');
        let finalizeBtn = this.modal.querySelector('#finalize-btn');

        this.backBtn.style.display = (this.currentStep > 0 && this.currentStep !== 1) ?
            'block' : 'none';
        this.nextBtn.style.display = this.currentStep < 1 ? 'block' : 'none';
        this.nextBtn.disabled = !this.serverTempFilePath;
        if (this.currentStep === 2) {
            if (!finalizeBtn) {
                const btnHTML =
                    `<button id="finalize-btn" class="accent-btn">Finalize Ingestion</button>`;
                finalizeContainer.insertAdjacentHTML('beforeend', btnHTML);
                this.modal.querySelector('#finalize-btn')
                    .addEventListener('click', () => this.finalizeImageIngestion());
            }
        } else {
            if (finalizeBtn) finalizeBtn.remove();
        }

        this.nextBtn.textContent = 'Next';
        const title = document.getElementById('import-wizard-title');
        const name = this.knowledgeBaseName;
        title.textContent = name ? `Importing: ${name}` : 'Import Knowledge Wizard';
    }

    logProgress(message) {
        if (!this.progressLog) return;
        const timestamp = new Date().toLocaleTimeString();
        this.progressLog.textContent += `[${timestamp}] ${message}\n`;
        this.progressLog.scrollTop = this.progressLog.scrollHeight;
    }

    async handleNext() {
        if (this.currentStep === 0) {
            this.knowledgeBaseName = document.getElementById('kb-name').value.trim();
            const msg = "Please provide a name for the knowledge base.";
            if (!this.knowledgeBaseName) return status.setText(msg, true);
            if (!this.serverTempFilePath) return status.setText("Please upload a file first.", true);
            this.navigate(1);
            await this.runFullIngestionProcess();
        }
    }

    async _uploadFile(file) {
        this.serverTempFilePath = null;
        this.nextBtn.disabled = true;
        this.uploadText.textContent = `Uploading ${file.name}...`;
        this.uploadText.classList.add('has-file');

        const formData = new FormData();
        formData.append('file', file);
        try {
            const result = await apiCall('/api/knowledge/upload-temp-file', {
                method: 'POST',
                body: formData
            });
            this.serverTempFilePath = result.temp_file_path;
            this.uploadText.textContent = `✔ ${file.name} (Ready)`;
            this.nextBtn.disabled = false;
        } catch (error) {
            this.uploadText.textContent = `✖ Upload Failed`;
            // apiCall helper shows the status bar error
        }
    }

    async runFullIngestionProcess() {
        this.progressLog = document.getElementById('wizard-progress-log');
        this.progressLog.textContent = ''; // Clear log
        try {
            this.isProcessing = true;
            this.spinner.style.display = 'block';
            const payload = {
                temp_file_path: this.serverTempFilePath,
                metadata: {
                    kb_name: this.knowledgeBaseName,
                    kb_type: document.getElementById('kb-type').value,
                    description: document.getElementById('kb-desc').value.trim(),
                    language: document.getElementById('kb-lang').value,
                    filename: this.selectedFile.name
                }
            };
            const response = await fetch('/api/knowledge/ingest-document', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            await this._processStream(response);

            const isPdf = this.selectedFile.name.toLowerCase().endsWith('.pdf');
            if (isPdf) {
                await this.loadImagesForReview();
                if (this.reviewImages.length > 0) {
                    const msg = `✔ Found ${this.reviewImages.length} images to review.`;
                    this.logProgress(msg);
                    this.navigate(1); // Move to step 2 (review)
                } else {
                    this.logProgress("No images found for review.");
                    this.logProgress("✔ Knowledge base created successfully.");
                    this.logProgress("All processes finished. You may now close this window.");
                }
            } else {
                this.logProgress("✔ Knowledge base created successfully.");
                this.logProgress("All processes finished. You may now close this window.");
            }
        } catch (error) {
            this.logProgress(`✖ ERROR: ${error.message}`);
        } finally {
            this.isProcessing = false;
            this.spinner.style.display = 'none';
        }
    }

    async _processStream(response) {
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();
            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                try {
                    const data = JSON.parse(line.substring(6));
                    if (data.error) throw new Error(data.error);
                    if (data.message) this.logProgress(data.message);
                } catch (e) {
                    console.error("Failed to parse stream chunk:", line, e);
                    this.logProgress(`✖ ERROR: ${e.message}`);
                    throw e; // Re-throw to be caught by the calling function
                }
            }
        }
    }

    async loadImagesForReview() {
        const url = `/api/knowledge/review-images/${this.knowledgeBaseName}`;
        this.reviewImages = await apiCall(url);

        if (this.reviewImages && this.reviewImages.length > 0) {
            this._initReviewListeners();
            this.currentReviewIndex = 0;
            this.displayReviewImage();
        }
    }

    displayReviewImage() {
        if (this.reviewImages.length === 0) {
            this.finalizeImageIngestion();
            return;
        }
        const newIdx = this.currentReviewIndex;
        this.currentReviewIndex = Math.max(0, Math.min(newIdx, this.reviewImages.length - 1));
        const current = this.reviewImages[this.currentReviewIndex];
        this.reviewImage.src = `${current.url}?t=${new Date().getTime()}`;
        const count = `${this.currentReviewIndex + 1} / ${this.reviewImages.length}`;
        this.reviewCounter.textContent = count;
        this.imgDesc.value = current.metadata.description;

        const selector = `input[name="image-classification"][value="${current.metadata.classification}"]`;
        const radioToSelect = this.modal.querySelector(selector);
        if (radioToSelect) {
            radioToSelect.checked = true;
        }

        document.getElementById('image-save-status').textContent = '';
        this.prevImgBtn.disabled = this.currentReviewIndex === 0;
        this.nextImgBtn.disabled = this.currentReviewIndex === this.reviewImages.length - 1;
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
        const classification =
            this.modal.querySelector('input[name="image-classification"]:checked').value;
        const payload = {
            description: this.imgDesc.value.trim(),
            classification: classification,
        };
        try {
            statusEl.textContent = 'Saving...';
            const url = `/api/knowledge/review-images/${this.knowledgeBaseName}/${current.filename}`;
            const opts = {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload)
            };
            await apiCall(url, opts);
            current.metadata.description = payload.description;
            current.metadata.classification = payload.classification;
            statusEl.textContent = 'Saved!';
            setTimeout(() => statusEl.textContent = '', 2000);
        } catch(error) {
            statusEl.textContent = `Error!`;
        }
    }

    async discardCurrentImage() {
        const current = this.reviewImages[this.currentReviewIndex];
        const msg = `Are you sure you want to discard this image?\n\n(${current.filename})`;
        if (confirm(msg)) {
            try {
                const url = `/api/knowledge/review-images/${this.knowledgeBaseName}/${current.filename}`;
                await apiCall(url, { method: 'DELETE' });
                this.reviewImages.splice(this.currentReviewIndex, 1);
                this.displayReviewImage(); // Refresh the view
            } catch (error) {
                // apiCall helper already shows alert
            }
        }
    }

    async finalizeImageIngestion() {
        const finalizeBtn = this.modal.querySelector('#finalize-btn');
        if (finalizeBtn) {
            finalizeBtn.disabled = true;
            finalizeBtn.textContent = 'Finalizing...';
        }

        try {
            await apiCall('/api/knowledge/ingest-images', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ kb_name: this.knowledgeBaseName })
            });
            status.setText("Knowledge base with images created successfully.");
            this.close();
        } catch (error) {
            if (finalizeBtn) finalizeBtn.disabled = false;
        }
    }

    preventDefaults(e) { e.preventDefault(); e.stopPropagation(); }
    highlight() { this.uploadArea.classList.add('drag-over'); }
    unhighlight() { this.uploadArea.classList.remove('drag-over'); }
    handleFileDrop(e) { this.handleFileSelect(e.dataTransfer.files); }

    handleFileSelect(files) {
        if (files.length > 0) {
            this.selectedFile = files[0];
            this._uploadFile(this.selectedFile);
        }
    }
}
