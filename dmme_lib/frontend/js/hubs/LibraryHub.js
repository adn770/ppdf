// dmme_lib/frontend/js/hubs/LibraryHub.js
import { apiCall } from '../wizards/ApiHelper.js';
import { status, confirmationModal } from '../ui.js';

export class LibraryHub {
    constructor(appInstance) {
        this.app = appInstance;
        this.isInitialized = false;
        this.selectedKb = null;

        this.view = document.getElementById('library-view');
        this.listEl = document.getElementById('kb-list-hub');
        this.inspector = document.getElementById('library-inspector');
        this.placeholder = document.getElementById('library-inspector-placeholder');
        this.content = document.getElementById('library-inspector-content');
        this.textView = document.getElementById('library-text-view');
        this.assetView = document.getElementById('library-asset-view');
        this.assetGrid = document.getElementById('asset-grid-container');
        this.dropzone = document.getElementById('asset-upload-dropzone');
        this.tabs = this.inspector.querySelectorAll('.hub-tab-btn');
    }

    init() {
        if (this.isInitialized) return;
        this.loadKnowledgeBases();
        this.tabs.forEach(tab => {
            tab.addEventListener('click', () => this.switchTab(tab.dataset.pane));
        });
        this._addDragDropListeners();
        this.listEl.addEventListener('click', (e) => this._handleKbDelete(e));
        this.assetGrid.addEventListener('click', (e) => this._handleAssetDelete(e));
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
                <button class="delete-icon-btn" data-kb-name="${kb.name}">🗑️</button>
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
        this.textView.querySelector('.hub-pane-wrapper').innerHTML = `<div class="spinner"></div>`;
        this.assetGrid.innerHTML = `<div class="spinner"></div>`;
        try {
            const data = await apiCall(`/api/knowledge/explore/${kb.name}`);
            this.renderTextView(data.documents);
            this.renderAssetView(data.assets);
        } catch (error) {
            this.textView.querySelector('.hub-pane-wrapper').innerHTML = `<p class="error">Failed to load content.</p>`;
            this.assetGrid.innerHTML = `<p class="error">Failed to load assets.</p>`;
        }
    }

    renderTextView(documents) {
        const wrapper = this.textView.querySelector('.hub-pane-wrapper');
        wrapper.innerHTML = '';
        if (!documents || documents.length === 0) {
            wrapper.innerHTML = `<p>No text documents found in this knowledge base.</p>`;
            return;
        }

        documents.forEach(doc => {
            const card = document.createElement('div');
            card.className = 'text-chunk-card';
            card.innerHTML = `
                <div class="text-chunk-content">${doc.document}</div>
                <div class="text-chunk-header">
                    <span class="text-chunk-label">${doc.label || 'PROSE'}</span>
                    <span>Source: ${doc.source_file}</span>
                </div>
            `;
            wrapper.appendChild(card);
        });
    }

    renderAssetView(assets) {
        this.assetGrid.innerHTML = '';
        if (!assets || assets.length === 0) {
            this.assetGrid.innerHTML = `<p>${this.app.i18n.t('noAssetsFound')}</p>`;
            return;
        }

        assets.forEach(asset => this._addAssetToGrid(asset, false));
    }

    _addAssetToGrid(asset, isNew = true) {
        if (isNew && this.assetGrid.querySelector('p')) {
            this.assetGrid.innerHTML = '';
        }

        const card = document.createElement('div');
        card.className = 'asset-card';
        card.innerHTML = `
            <img src="${asset.url}" alt="${asset.caption}" title="${asset.caption}">
            <p>${asset.classification}</p>
            <button class="delete-asset-btn" data-filename="${asset.thumb_filename}" title="Delete Asset">🗑️</button>
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

    async _handleKbDelete(event) {
        const deleteBtn = event.target.closest('.delete-icon-btn');
        if (!deleteBtn) return;

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

    async _handleAssetDelete(event) {
        const deleteBtn = event.target.closest('.delete-asset-btn');
        if (!deleteBtn) return;

        const thumbFilename = deleteBtn.dataset.filename;
        const confirmed = await confirmationModal.confirm(
            'deleteAssetTitle',
            'deleteAssetMsg',
            { filename: thumbFilename }
        );

        if (confirmed) {
            try {
                const response = await fetch(`/api/knowledge/${this.selectedKb.name}/asset/${thumbFilename}`, {
                    method: 'DELETE'
                });
                if (!response.ok) {
                    const errorData = await response.json();
                    throw new Error(errorData.error || `HTTP Error: ${response.status}`);
                }
                deleteBtn.closest('.asset-card').remove();
                status.setText('deleteAssetSuccess', false, { filename: thumbFilename });
            } catch (error) {
                status.setText(error.message, true);
            }
        }
    }

    switchTab(paneName) {
        this.tabs.forEach(tab => {
            tab.classList.toggle('active', tab.dataset.pane === paneName);
        });
        this.inspector.querySelectorAll('.hub-tab-pane').forEach(pane => {
            // BUG FIX: The asset pane ID is singular, but the data-pane value is plural.
            // This ensures the correct ID is targeted.
            const targetPane = paneName === 'assets' ? 'asset' : paneName;
            const paneId = `library-${targetPane}-view`;
            pane.classList.toggle('active', pane.id === paneId);
        });
    }
}
