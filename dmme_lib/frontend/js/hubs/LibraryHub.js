// dmme_lib/frontend/js/hubs/LibraryHub.js
import { apiCall } from '../wizards/ApiHelper.js';
import { status, confirmationModal } from '../ui.js';

export class LibraryHub {
    constructor(appInstance, lightboxInstance) {
        this.app = appInstance;
        this.lightbox = lightboxInstance;
        this.isInitialized = false;
        this.selectedKb = null;
        this.kbDataCache = {}; // Cache for explore and entity data
    }

    _setupElements() {
        this.view = document.getElementById('library-view');
        this.listEl = document.getElementById('kb-list-hub');
        this.inspector = document.getElementById('library-inspector');
        this.placeholder = document.getElementById('library-inspector-placeholder');
        this.content = document.getElementById('library-inspector-content');
        this.tabs = this.inspector.querySelectorAll('.hub-tab-btn');
        this.panes = this.inspector.querySelectorAll('.hub-tab-pane');

        this.dashboardView = document.getElementById('library-dashboard-view');
        this.chunkCountEl = document.getElementById('dashboard-chunk-count');
        this.entityChartEl = document.getElementById('dashboard-entity-chart');
        this.wordCloudEl = document.getElementById('dashboard-word-cloud');

        this.contentView = document.getElementById('library-content-view');
        this.contentListEl = document.getElementById('content-explorer-list');

        this.entitiesView = document.getElementById('library-entities-view');
        this.entityFilterInput = document.getElementById('entity-filter-input');
        this.entityMasterList = document.getElementById('entity-master-list');
        this.entityDetailsPanel = document.getElementById('entity-details-panel');
        this.entityDetailsPlaceholder = document.getElementById('entity-details-placeholder');
        this.entityRelatedChunks = document.getElementById('entity-related-chunks');

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
        this.entityFilterInput.addEventListener('input', () => this._filterEntityList());
        this.entityMasterList.addEventListener('click', (e) => this._handleEntitySelection(e));
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
        if (this.selectedKb?.name === kb.name) return;
        this.selectedKb = kb;
        this.kbDataCache[kb.name] = {}; // Clear cache for new selection

        this.listEl.querySelectorAll('li').forEach(li => {
            li.classList.toggle('selected', li.dataset.kbName === kb.name);
        });
        this.placeholder.style.display = 'none';
        this.content.style.display = 'flex';
        this.switchTab('dashboard');
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
            const weight = (term.value - min) / (max - min || 1);
            const fontSize = 0.8 + weight * 1.2; // From 0.8rem to 2.0rem
            span.style.fontSize = `${fontSize}rem`;
            this.wordCloudEl.appendChild(span);
        });
    }

    async renderContentView() {
        const wrapper = this.contentView.querySelector('.hub-pane-wrapper');
        wrapper.innerHTML = '<div class="spinner"></div>';
        const data = await this._getKbExploreData();
        wrapper.innerHTML = '';

        if (!data.documents || data.documents.length === 0) {
            wrapper.innerHTML = `<p>No text documents found in this knowledge base.</p>`;
            return;
        }
        data.documents.forEach(doc => {
            wrapper.insertAdjacentHTML('beforeend', this._createChunkCardHTML(doc));
        });
    }

    async renderEntityView() {
        const entities = await this._getKbEntityData();
        this.entityMasterList.innerHTML = '';
        this.entityDetailsPlaceholder.style.display = 'flex';
        this.entityRelatedChunks.style.display = 'none';
        this.entityFilterInput.value = '';

        if (!entities || entities.length === 0) {
            this.entityMasterList.innerHTML = '<li>No entities found.</li>';
            return;
        }

        entities.forEach(entity => {
            const li = document.createElement('li');
            li.dataset.entityName = entity;
            li.innerHTML = `<div class="item-main-content"><span>${entity}</span></div>`;
            this.entityMasterList.appendChild(li);
        });
    }

    _filterEntityList() {
        const filter = this.entityFilterInput.value.toLowerCase();
        this.entityMasterList.querySelectorAll('li').forEach(li => {
            const name = li.dataset.entityName.toLowerCase();
            li.style.display = name.includes(filter) ? '' : 'none';
        });
    }

    async _handleEntitySelection(event) {
        const li = event.target.closest('li[data-entity-name]');
        if (!li) return;

        this.entityMasterList.querySelectorAll('li').forEach(el => el.classList.remove('selected'));
        li.classList.add('selected');

        const entityName = li.dataset.entityName;
        const data = await this._getKbExploreData();
        if (!data.documents) return;

        const relatedChunks = data.documents.filter(doc => {
            try {
                const entities = JSON.parse(doc.entities || '{}');
                return Object.keys(entities).includes(entityName);
            } catch (e) { return false; }
        });

        this.entityDetailsPlaceholder.style.display = 'none';
        this.entityRelatedChunks.style.display = 'flex';
        this.entityRelatedChunks.innerHTML = '';

        if (relatedChunks.length === 0) {
            this.entityRelatedChunks.innerHTML = `<p>No chunks found for "${entityName}".</p>`;
        } else {
            relatedChunks.forEach(doc => {
                this.entityRelatedChunks.insertAdjacentHTML('beforeend', this._createChunkCardHTML(doc));
            });
        }
    }

    _createChunkCardHTML(doc) {
        const label = doc.label || 'PROSE';
        const keyTerms = JSON.parse(doc.key_terms || '[]');
        const keyTermsHTML = keyTerms.map(term => `<span class="key-term-chip">${term}</span>`).join('');
        const hasLinks = JSON.parse(doc.linked_chunks || '[]').length > 0;
        const hasStats = doc.structured_stats && Object.keys(JSON.parse(doc.structured_stats)).length > 0;

        return `
        <div class="text-chunk-card">
            <div class="text-chunk-header">
                <span class="text-chunk-label">${label}</span>
                <span>${doc.source_file} (p. ${doc.page_start})</span>
            </div>
            <pre class="text-chunk-content">${doc.document}</pre>
            <div class="text-chunk-footer">
                <div class="key-terms-list">${keyTermsHTML}</div>
                <div class="metadata-icons">
                    ${hasLinks ? '<span title="Has linked content">🔗</span>' : ''}
                    ${hasStats ? '<span title="Has structured data">📊</span>' : ''}
                </div>
            </div>
        </div>`;
    }

    async renderAssetsView() {
        this.assetGrid.innerHTML = '<div class="spinner"></div>';
        const data = await this._getKbExploreData();
        this.assetGrid.innerHTML = '';
        if (!data.assets || data.assets.length === 0) {
            this.assetGrid.innerHTML = `<p>${this.app.i18n.t('noAssetsFound')}</p>`;
            return;
        }
        data.assets.forEach(asset => this._addAssetToGrid(asset, false));
    }

    async _getKbExploreData() {
        if (!this.kbDataCache[this.selectedKb.name]?.explore) {
            this.kbDataCache[this.selectedKb.name].explore = await apiCall(`/api/knowledge/explore/${this.selectedKb.name}`);
        }
        return this.kbDataCache[this.selectedKb.name].explore;
    }

    async _getKbEntityData() {
        if (!this.kbDataCache[this.selectedKb.name]?.entities) {
            this.kbDataCache[this.selectedKb.name].entities = await apiCall(`/api/knowledge/entities/${this.selectedKb.name}`);
        }
        return this.kbDataCache[this.selectedKb.name].entities;
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

        if (this.selectedKb) {
            if (paneName === 'dashboard') this.renderDashboard();
            if (paneName === 'content') this.renderContentView();
            if (paneName === 'entities') this.renderEntityView();
            if (paneName === 'assets') this.renderAssetsView();
        }
    }
}
