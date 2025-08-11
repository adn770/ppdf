// dmme_lib/frontend/js/wizards/ImportWizard.js
import { apiCall } from './ApiHelper.js';
import { status, confirmationModal } from '../ui.js';

export class ImportWizard {
    constructor(appInstance) {
        this.app = appInstance;
        this.currentStep = 0;
        this.totalSteps = 4; // 0:Details, 1:Review, 2:Processing, 3:ImageReview
        this.selectedFile = null;
        this.serverTempFilePath = null;
        this.knowledgeBaseName = '';
        this.reviewImages = [];
        this.currentReviewIndex = 0;
        this.uploadDefaultTextKey = 'wizardUploadArea';
        this.reviewListenersAttached = false;
        this.progressLog = null;
        this.isProcessing = false;
        this.importCompleted = false;
        this.autosaveDebounceTimer = null;

        this.modal = document.getElementById('import-wizard-modal');
        this.overlay = document.getElementById('modal-overlay');
        this.panes = this.modal.querySelectorAll('.wizard-pane');
        this.backBtn = document.getElementById('import-wizard-back-btn');
        this.nextBtn = document.getElementById('import-wizard-next-btn');
        this.uploadArea = document.getElementById('wizard-upload-area');
        this.uploadInput = document.getElementById('wizard-upload-input');
        this.uploadText = document.getElementById('wizard-upload-text');
        this.pdfPagesGroup = document.getElementById('pdf-pages-group');
        this.pdfPagesInput = document.getElementById('pdf-pages-input');
        this.extractImagesCheckbox = document.getElementById('extract-images-checkbox');
        this.reviewImage = document.getElementById('review-image');
        this.reviewCounter = document.getElementById('image-review-counter');
        this.imgDesc = document.getElementById('image-description');
        this.spinner = this.modal.querySelector('#wizard-pane-2 .spinner');
        this.sectionListEl = document.getElementById('wizard-section-list');
        this.selectAllBtn = document.getElementById('wizard-select-all-sections');
        this.deselectAllBtn = document.getElementById('wizard-deselect-all-sections');

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
        this.selectAllBtn.addEventListener('click', () => this._toggleAllSections(true));
        this.deselectAllBtn.addEventListener('click', () => this._toggleAllSections(false));
        this.sectionListEl.addEventListener('change', () => this._updateNextButtonState());
    }

    _initReviewListeners() {
        if (this.reviewListenersAttached) return;
        this.prevImgBtn = document.getElementById('image-prev-btn');
        this.nextImgBtn = document.getElementById('image-next-btn');
        this.discardImgBtn = document.getElementById('discard-image-btn');
        this.classificationRadios =
            this.modal.querySelectorAll('input[name="image-classification"]');
        this.prevImgBtn.addEventListener('click', () => this.navigateReviewImage(-1));
        this.nextImgBtn.addEventListener('click', () => this.navigateReviewImage(1));
        this.discardImgBtn.addEventListener('click', () => this.discardCurrentImage());
        // Autosave listeners
        this.imgDesc.addEventListener('input', () => this.debouncedSaveImageChanges());
        this.classificationRadios.forEach(radio => {
            radio.addEventListener('change', () => this.saveImageChanges());
        });
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
        if (this.importCompleted) {
            this.app.libraryHub.loadKnowledgeBases();
        }
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
        this.uploadText.textContent = this.app.i18n.t(this.uploadDefaultTextKey);
        this.uploadText.classList.remove('has-file');
        this.uploadInput.value = '';
        document.getElementById('kb-name').value = '';
        document.getElementById('kb-desc').value = '';
        this.pdfPagesInput.value = 'all';
        this.pdfPagesInput.disabled = true;
        this.extractImagesCheckbox.checked = true;
        this.extractImagesCheckbox.disabled = true;
        this.unhighlight();
        this.progressLog = null;
        this.isProcessing = false;
        this.importCompleted = false;
        this.updateView();
    }

    navigate(direction) {
        const newStep = this.currentStep + direction;
        this.currentStep = Math.max(0, Math.min(newStep, this.totalSteps - 1));
        this.updateView();
    }

    updateView() {
        const i18n = this.app.i18n;
        this.panes.forEach((pane, index) => {
            pane.classList.toggle('active', index === this.currentStep);
        });
        const finalizeContainer = this.modal.querySelector('.modal-footer');
        let finalizeBtn = this.modal.querySelector('#finalize-btn');

        this.backBtn.style.display = (this.currentStep > 0 && this.currentStep !== 2) ?
            'block' : 'none';
        this.nextBtn.style.display = this.currentStep < 2 ? 'block' : 'none';
        if (this.currentStep === 3) { // Image review pane
            if (!finalizeBtn) {
                const btnHTML =
                    `<button id="finalize-btn" class="accent-btn" data-i18n-key="wizardFinalize">Finalize Ingestion</button>`;
                finalizeContainer.insertAdjacentHTML('beforeend', btnHTML);
                finalizeBtn = this.modal.querySelector('#finalize-btn');
                finalizeBtn.addEventListener('click', () => this.finalizeImageIngestion());
            }
        } else {
            if (finalizeBtn) finalizeBtn.remove();
        }

        this.nextBtn.textContent = i18n.t('wizardNext');
        const title = document.getElementById('import-wizard-title');
        const name = this.knowledgeBaseName;
        const titleKey = name ? 'importWizardTitleWithName' : 'importWizardTitle';
        title.textContent = i18n.t(titleKey, { name });
        this._updateNextButtonState();
    }

    _updateNextButtonState() {
        if (this.currentStep === 0) {
            this.nextBtn.disabled = !this.serverTempFilePath;
        } else if (this.currentStep === 1) {
            const selectedCount = this.sectionListEl.querySelectorAll('input:checked').length;
            this.nextBtn.disabled = selectedCount === 0;
        }
    }

    _toggleAllSections(checkedState) {
        this.sectionListEl.querySelectorAll('input[type="checkbox"]').forEach(cb => {
            cb.checked = checkedState;
        });
        this._updateNextButtonState();
    }

    _renderSectionList(sections = []) {
        this.sectionListEl.innerHTML = '';
        if (sections.length === 0) {
            this.sectionListEl.innerHTML = `<p>No sections found for review.</p>`;
            return;
        }

        sections.forEach((section, index) => {
            const item = document.createElement('div');
            item.className = 'section-item';
            const sectionTitle = section.title || 'Untitled Section';
            item.innerHTML = `
                <input type="checkbox" id="section-${index}" data-section-title="${sectionTitle}" checked>
                <label for="section-${index}" class="section-item-label">
                    <span class="section-item-title">${sectionTitle}</span>
                    <span class="section-item-details">Pages: ${section.page_start}-${section.page_end}</span>
                </label>
                <span class="section-item-stats">${(section.char_count || 0).toLocaleString()} chars</span>
            `;
            this.sectionListEl.appendChild(item);
        });
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
            if (!this.knowledgeBaseName) return status.setText('errorKbName', true);
            if (!this.serverTempFilePath) return status.setText('errorFile', true);

            const isPdf = this.selectedFile.name.toLowerCase().endsWith('.pdf');
            if (!isPdf) {
                // For non-PDFs, skip analysis and go straight to processing.
                this.navigate(2);
                await this.runFullIngestionProcess();
                return;
            }

            this.sectionListEl.innerHTML = '<div class="spinner spinner-lg"></div>';
            this.navigate(1); // Move to review pane

            try {
                const payload = {
                    temp_file_path: this.serverTempFilePath,
                    pages: this.pdfPagesInput.value.trim() || 'all'
                };
                const sections = await apiCall('/api/knowledge/analyze', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                this._renderSectionList(sections);
            } catch (error) {
                this.sectionListEl.innerHTML = `<p class="error">Failed to analyze document.</p>`;
            } finally {
                this._updateNextButtonState();
            }

        } else if (this.currentStep === 1) {
            const sectionsToInclude = Array.from(
                this.sectionListEl.querySelectorAll('input:checked')
            ).map(cb => cb.dataset.sectionTitle);
            this.navigate(1); // Move to processing pane (now step 2)
            await this.runFullIngestionProcess(sectionsToInclude);
        }
    }

    async _uploadFile(file) {
        this.serverTempFilePath = null;
        this.nextBtn.disabled = true;
        this.uploadText.textContent = this.app.i18n.t('wizardUploading', {filename: file.name});
        this.uploadText.classList.add('has-file');

        const formData = new FormData();
        formData.append('file', file);
        try {
            const result = await apiCall('/api/knowledge/upload-temp-file', {
                method: 'POST',
                body: formData
            });
            this.serverTempFilePath = result.temp_file_path;
            this.uploadText.textContent = this.app.i18n.t('wizardUploadAreaHasFile', {filename: file.name});
            this.nextBtn.disabled = false;
        } catch (error) {
            this.uploadText.textContent = this.app.i18n.t('wizardUploadFailed');
        }
    }

    async runFullIngestionProcess(sectionsToInclude = null) {
        this.progressLog = document.getElementById('wizard-progress-log');
        this.progressLog.textContent = ''; // Clear log
        try {
            this.isProcessing = true;
            this.spinner.style.display = 'block';
            const pagesValue = this.pdfPagesInput.value.trim();
            const payload = {
                temp_file_path: this.serverTempFilePath,
                pages: pagesValue || 'all',
                sections_to_include: sectionsToInclude,
                extract_images: this.extractImagesCheckbox.checked,
                deep_indexing: document.getElementById('deep-indexing-checkbox').checked,
                force_paragraph_chunking: document.getElementById('force-paragraph-chunking-checkbox').checked,
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
            if (isPdf && this.extractImagesCheckbox.checked) {
                await this.loadImagesForReview();
                if (this.reviewImages.length > 0) {
                    const msg = `✔ Found ${this.reviewImages.length} images to review.`;
                    this.logProgress(msg);
                    this.navigate(1); // Move to step 3 (image review)
                } else {
                    this.logProgress("No images found for review.");
                    this.logProgress("✔ Knowledge base created successfully.");
                    this.logProgress("All processes finished. You may now close this window.");
                    this.importCompleted = true;
                }
            } else {
                this.logProgress("✔ Knowledge base created successfully.");
                this.logProgress("All processes finished. You may now close this window.");
                this.importCompleted = true;
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

        // Explicitly set the checked state for all radio buttons
        this.classificationRadios.forEach(radio => {
            radio.checked = radio.value === current.metadata.classification;
        });
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

    debouncedSaveImageChanges() {
        clearTimeout(this.autosaveDebounceTimer);
        this.autosaveDebounceTimer = setTimeout(() => {
            this.saveImageChanges();
        }, 500);
        // Wait 500ms after user stops typing
    }

    async saveImageChanges() {
        const current = this.reviewImages[this.currentReviewIndex];
        const classification =
            this.modal.querySelector('input[name="image-classification"]:checked').value;
        const payload = {
            description: this.imgDesc.value.trim(),
            classification: classification,
        };
        try {
            console.log("Autosaving image metadata...", payload);
            const url = `/api/knowledge/review-images/${this.knowledgeBaseName}/${current.filename}`;
            const opts = {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload)
            };
            await apiCall(url, opts);
            // Update local data to match
            current.metadata.description = payload.description;
            current.metadata.classification = payload.classification;
        } catch(error) {
            console.error("Failed to autosave image metadata:", error);
        }
    }

    async discardCurrentImage() {
        const current = this.reviewImages[this.currentReviewIndex];
        const confirmed = await confirmationModal.confirm(
            'deleteImageTitle',
            'deleteImageMsg',
            { filename: current.filename }
        );
        if (confirmed) {
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
            finalizeBtn.setAttribute('data-i18n-key', 'wizardFinalizing');
            finalizeBtn.textContent = this.app.i18n.t('wizardFinalizing');
        }

        try {
            await apiCall('/api/knowledge/ingest-images', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ kb_name: this.knowledgeBaseName })
            });
            status.setText("Knowledge base with images created successfully.");
            this.importCompleted = true;
            this.close();
        } catch (error) {
            if (finalizeBtn) {
                 finalizeBtn.disabled = false;
                 finalizeBtn.setAttribute('data-i18n-key', 'wizardFinalize');
                 finalizeBtn.textContent = this.app.i18n.t('wizardFinalize');
            }
        }
    }

    preventDefaults(e) { e.preventDefault(); e.stopPropagation(); }
    highlight() { this.uploadArea.classList.add('drag-over'); }
    unhighlight() { this.uploadArea.classList.remove('drag-over'); }
    handleFileDrop(e) { this.handleFileSelect(e.dataTransfer.files); }

    handleFileSelect(files) {
        if (files.length > 0) {
            this.selectedFile = files[0];
            const isPdf = this.selectedFile.name.toLowerCase().endsWith('.pdf');
            this.pdfPagesInput.disabled = !isPdf;
            this.extractImagesCheckbox.disabled = !isPdf;
            this._uploadFile(this.selectedFile);
        }
    }
}
