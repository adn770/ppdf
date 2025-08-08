// dmme_lib/frontend/js/hubs/LibraryHub.js
import { apiCall } from '../wizards/ApiHelper.js';
import { status, confirmationModal } from '../ui.js';

export class LibraryHub {
    constructor(appInstance, lightboxInstance) {
        this.app = appInstance;
        this.lightbox = lightboxInstance;
        this.isInitialized = false;
        this.selectedKb = null;
    }

    _setupElements() {
        this.view = document.getElementById('library-view');
        this.listEl = document.getElementById('kb-list-hub');
        this.inspector = document.getElementById('library-inspector');
        this.placeholder = document.getElementById('library-inspector-placeholder');
        this.content = document.getElementById('library-inspector-content');
        this.tabs = this.inspector.querySelectorAll('.hub-tab-btn');
        this.panes = this.inspector.querySelectorAll('.hub-tab-pane');

        // New Dashboard elements
        this.dashboardView = document.getElementById('library-dashboard-view');
        this.chunkCountEl = document.getElementById('dashboard-chunk-count');
        this.entityChartEl = document.getElementById('dashboard-entity-chart');
        this.wordCloudEl = document.getElementById('dashboard-word-cloud');

        // Old view elements (for future milestones)
        this.contentView = document.getElementById('library-content-view');
        this.assetsView = document.getElementById('library-assets-view');
        this.assetGrid = document.getElementById('asset-grid-container');
        this.dropzone = document.getElementById('asset-upload-dropzone');
    }

    init() {
        if (this.isInitialized) return;
        this._setupElements();
        this.loadKnowledgeBases();
        this.tabs.forEach(tab => {
            tab.addEventListener('click', () => this.switchTab(tab.dataset.pane));
        });
        this._addDragDropListeners();
        this.listEl.addEventListener('click', (e) => this._handleKbListInteraction(e));
        this.assetGrid.addEventListener('click', (e) => this._handleAssetInteraction(e));
        this.isInitialized = true;
    }

    _preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    _addDragDropListeners() {
        const events = ['dragenter', 'dragover', 'dragleave', 'drop'];
        events.forEach(eventName => {
            this.dropzone.addEventListener(eventName, this._preventDefaults, false);
            document.body.addEventListener(eventName, this._preventDefaults, false);
        });
        ['dragenter', 'dragover'].forEach(eventName => {
            this.dropzone.addEventListener(eventName, () => this.dropzone.classList.add('drag-over'), false);
        });
        ['dragleave', 'drop'].forEach(eventName => {
            this.dropzone.addEventListener(eventName, () => this.dropzone.classList.remove('drag-over'), false);
        });
        this.dropzone.addEventListener('drop', (e) => this._handleFileDrop(e), false);
    }

    async loadKnowledgeBases() {
        this.listEl.innerHTML = `<li>${this.app.i18n.t('kbMgmtLoading')}</li>`;
        try {
            const kbs = await apiCall('/api/knowledge/');
            this.renderKbList(kbs);
        } catch (error) {
            this.listEl.innerHTML = `<li class="error">${this.app.i18n.t('kbMgmtFailed')}</li>`;
        }
    }

    renderKbList(kbs) {
        this.listEl.innerHTML = '';
        if (kbs.length === 0) {
            this.listEl.innerHTML = `<li>${this.app.i18n.t('kbMgmtEmpty')}</li>`;
            return;
        }

        kbs.forEach(kb => {
            const li = document.createElement('li');
            li.dataset.kbName = kb.name;
            const metadata = kb.metadata || {};
            const type = metadata.kb_type || 'N/A';
            const lang = metadata.language || 'N/A';

            li.innerHTML = `
                <div class="item-main-content">
                    <span>${kb.name}</span>
                    <div class="item-details">
                        ${type.toUpperCase()} | ${lang.toUpperCase()} | ${kb.count} docs
                    </div>
                </div>
                <button class="contextual-delete-btn slide-in-right" data-kb-name="${kb.name}">
                    <span class="icon">&times;</span>
                    <span data-i18n-key="deleteBtn">${this.app.i18n.t('deleteBtn')}</span>
                </button>
            `;
            li.querySelector('.item-main-content').addEventListener('click', () => this.showKbDetails(kb));
            this.listEl.appendChild(li);
        });
    }

    async showKbDetails(kb) {
        this.selectedKb = kb;
        this.listEl.querySelectorAll('li').forEach(li => {
            li.classList.toggle('selected', li.dataset.kbName === kb.name);
        });
        this.placeholder.style.display = 'none';
        this.content.style.display = 'flex';
        this.switchTab('dashboard'); // Default to dashboard view
        this.renderDashboard();
    }

    async renderDashboard() {
        this.chunkCountEl.textContent = '...';
        this.entityChartEl.innerHTML = '<div class="spinner"></div>';
        this.wordCloudEl.innerHTML = '<div class="spinner"></div>';
        try {
            const data = await apiCall(`/api/knowledge/dashboard/${this.selectedKb.name}`);
            this.chunkCountEl.textContent = data.chunk_count.toLocaleString();
            this._renderEntityChart(data.entity_distribution);
            this._renderWordCloud(data.key_terms_word_cloud);
        } catch (error) {
            this.chunkCountEl.textContent = 'Error';
            this.entityChartEl.innerHTML = '<p class="error">Failed to load chart.</p>';
            this.wordCloudEl.innerHTML = '<p class="error">Failed to load terms.</p>';
        }
    }

    _renderEntityChart(distribution) {
        this.entityChartEl.innerHTML = '';
        const total = Object.values(distribution).reduce((sum, count) => sum + count, 0);
        if (total === 0) {
            this.entityChartEl.innerHTML = '<p>No entities found.</p>';
            return;
        }

        for (const [entity, count] of Object.entries(distribution)) {
            const percentage = (count / total) * 100;
            const row = document.createElement('div');
            row.className = 'chart-bar-row';
            row.innerHTML = `
                <span class="chart-bar-label">${entity}</span>
                <div class="chart-bar-wrapper">
                    <div class="chart-bar" style="width: ${percentage}%;"></div>
                </div>
                <span class="chart-bar-value">${count}</span>
            `;
            this.entityChartEl.appendChild(row);
        }
    }

    _renderWordCloud(terms) {
        this.wordCloudEl.innerHTML = '';
        if (!terms || terms.length === 0) {
            this.wordCloudEl.innerHTML = '<p>No key terms found.</p>';
            return;
        }

        const counts = terms.map(t => t.value);
        const min = Math.min(...counts);
        const max = Math.max(...counts);

        terms.forEach(term => {
            const span = document.createElement('span');
            span.textContent = term.text;
            // Normalize font size between a min and max
            const weight = (term.value - min) / (max - min || 1);
            const fontSize = 0.8 + weight * 1.2; // From 0.8rem to 2.0rem
            span.style.fontSize = `${fontSize}rem`;
            this.wordCloudEl.appendChild(span);
        });
    }

    // This logic will be fully implemented in a later milestone
    async renderContentView() {
        const wrapper = this.contentView.querySelector('.hub-pane-wrapper');
        wrapper.innerHTML = '<div class="spinner"></div>';
        const data = await apiCall(`/api/knowledge/explore/${this.selectedKb.name}`);
        wrapper.innerHTML = '';
        if (!data.documents || data.documents.length === 0) {
            wrapper.innerHTML = `<p>No text documents found in this knowledge base.</p>`;
            return;
        }
        data.documents.forEach(doc => {
            const card = document.createElement('div');
            card.className = 'text-chunk-card';
            // Placeholder for new rich card design
            card.textContent = JSON.stringify(doc, null, 2);
            wrapper.appendChild(card);
        });
    }

    // This logic will be fully implemented in a later milestone
    async renderAssetsView() {
        this.assetGrid.innerHTML = '<div class="spinner"></div>';
        const data = await apiCall(`/api/knowledge/explore/${this.selectedKb.name}`);
        this.assetGrid.innerHTML = '';
        if (!data.assets || data.assets.length === 0) {
            this.assetGrid.innerHTML = `<p>${this.app.i18n.t('noAssetsFound')}</p>`;
            return;
        }
        data.assets.forEach(asset => this._addAssetToGrid(asset, false));
    }

    _addAssetToGrid(asset, isNew = true) {
        if (isNew && this.assetGrid.querySelector('p')) {
            this.assetGrid.innerHTML = '';
        }
        const card = document.createElement('div');
        card.className = 'asset-card';
        card.dataset.fullUrl = asset.full_url;
        card.innerHTML = `
            <img src="${asset.thumb_url}" alt="${asset.description}" title="${asset.description}">
            <p>${asset.classification}</p>
            <button class="contextual-delete-btn slide-in-bottom" data-thumb-filename="${asset.thumb_url.split('/').pop()}">
                <span class="icon">&times;</span>
                <span data-i18n-key="deleteBtn">${this.app.i18n.t('deleteBtn')}</span>
            </button>
        `;
        this.assetGrid.appendChild(card);
    }

    _handleFileDrop(e) {
        if (!this.selectedKb) {
            status.setText('errorSelectKbForUpload', true);
            return;
        }
        const files = e.dataTransfer.files;
        for (const file of files) {
            if (file.type.startsWith('image/')) {
                this._uploadFile(file);
            }
        }
    }

    async _uploadFile(file) {
        const dropzoneText = this.dropzone.querySelector('p');
        dropzoneText.textContent = `Uploading ${file.name}...`;

        const formData = new FormData();
        formData.append('file', file);
        try {
            const response = await fetch(`/api/knowledge/${this.selectedKb.name}/upload-asset`, {
                method: 'POST',
                body: formData,
            });
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
            }

            const newAsset = await response.json();
            this._addAssetToGrid(newAsset, true);
            status.setText('assetUploadSuccess', false, { filename: file.name });
        } catch (error) {
            status.setText(`Error: ${error.message}`, true);
        } finally {
            setTimeout(() => {
                dropzoneText.textContent = this.app.i18n.t('dropzoneText');
            }, 3000);
        }
    }

    _handleAssetInteraction(event) {
        const deleteBtn = event.target.closest('.contextual-delete-btn');
        if (deleteBtn) {
            event.stopPropagation();
            this._handleAssetDelete(deleteBtn);
        } else {
            const card = event.target.closest('.asset-card');
            if (card && card.dataset.fullUrl) {
                this.lightbox.open(card.dataset.fullUrl);
            }
        }
    }

    async _handleKbListInteraction(event) {
        const deleteBtn = event.target.closest('.contextual-delete-btn');
        if (deleteBtn) {
            const kbName = deleteBtn.dataset.kbName;
            const confirmed = await confirmationModal.confirm(
                'deleteKbTitle',
                'deleteKbMsg',
                { name: kbName }
            );
            if (confirmed) {
                await apiCall(`/api/knowledge/${kbName}`, { method: 'DELETE' });
                status.setText('deleteKbSuccess', false, { name: kbName });
                if (this.selectedKb && this.selectedKb.name === kbName) {
                    this.placeholder.style.display = 'flex';
                    this.content.style.display = 'none';
                    this.selectedKb = null;
                }
                await this.loadKnowledgeBases();
            }
        }
    }

    async _handleAssetDelete(deleteBtn) {
        const thumbFilename = deleteBtn.dataset.thumbFilename;
        const confirmed = await confirmationModal.confirm(
            'deleteAssetTitle',
            'deleteAssetMsg',
            { filename: thumbFilename }
        );
        if (confirmed) {
            try {
                const url = `/api/knowledge/${this.selectedKb.name}/asset/${thumbFilename}`;
                await apiCall(url, { method: 'DELETE' });
                deleteBtn.closest('.asset-card').remove();
                status.setText('deleteAssetSuccess', false, { filename: thumbFilename });
            } catch (error) {
                // Status is already shown by apiCall helper
            }
        }
    }

    switchTab(paneName) {
        this.tabs.forEach(tab => {
            tab.classList.toggle('active', tab.dataset.pane === paneName);
        });
        this.panes.forEach(pane => {
            const paneId = `library-${paneName}-view`;
            pane.classList.toggle('active', pane.id === paneId);
        });
        // Lazy-load content for non-dashboard tabs
        if (this.selectedKb) {
            if (paneName === 'content') this.renderContentView();
            if (paneName === 'assets') this.renderAssetsView();
        }
    }
}
