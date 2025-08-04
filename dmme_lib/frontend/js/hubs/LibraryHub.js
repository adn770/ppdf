// dmme_lib/frontend/js/hubs/LibraryHub.js
import { apiCall } from '../wizards/ApiHelper.js';

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
        this.tabs = this.inspector.querySelectorAll('.hub-tab-btn');
    }

    init() {
        if (this.isInitialized) return;
        this.loadKnowledgeBases();

        this.tabs.forEach(tab => {
            tab.addEventListener('click', () => this.switchTab(tab.dataset.pane));
        });

        this.isInitialized = true;
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
                <div>
                    <span>${kb.name}</span>
                    <div class="item-details">
                        ${type.toUpperCase()} | ${lang.toUpperCase()} | ${kb.count} docs
                    </div>
                </div>
            `;
            li.addEventListener('click', () => this.showKbDetails(kb));
            this.listEl.appendChild(li);
        });
    }

    async showKbDetails(kb) {
        this.selectedKb = kb;
        this.listEl.querySelectorAll('li').forEach(li => {
            li.classList.toggle('selected', li.dataset.kbName === kb.name);
        });

        this.placeholder.style.display = 'none';
        this.content.style.display = 'block';
        this.textView.innerHTML = `<div class="spinner"></div>`;
        this.assetView.innerHTML = `<div class="spinner"></div>`;

        try {
            const data = await apiCall(`/api/knowledge/explore/${kb.name}`);
            this.renderTextView(data.documents);
            this.renderAssetView(data.assets);
        } catch (error) {
            this.textView.innerHTML = `<p class="error">Failed to load content.</p>`;
            this.assetView.innerHTML = `<p class="error">Failed to load assets.</p>`;
        }
    }

    renderTextView(documents) {
        this.textView.innerHTML = '';
        if (!documents || documents.length === 0) {
            this.textView.innerHTML = `<p>No text documents found in this knowledge base.</p>`;
            return;
        }

        documents.forEach(doc => {
            const card = document.createElement('div');
            card.className = 'text-chunk-card';
            card.innerHTML = `
                <div class="text-chunk-header">
                    <span class="text-chunk-label">${doc.label || 'PROSE'}</span>
                    <span>Source: ${doc.source_file}</span>
                </div>
                <div class="text-chunk-content">
                    ${doc.document}
                </div>
            `;
            this.textView.appendChild(card);
        });
    }

    renderAssetView(assets) {
        this.assetView.innerHTML = '';
        if (!assets || assets.length === 0) {
            this.assetView.innerHTML = `<p>No assets found in this knowledge base.</p>`;
            return;
        }

        assets.forEach(asset => {
            const card = document.createElement('div');
            card.className = 'asset-card';
            card.innerHTML = `
                <img src="${asset.url}" alt="${asset.caption}" title="${asset.caption}">
                <p>${asset.classification}</p>
            `;
            this.assetView.appendChild(card);
        });
    }

    switchTab(paneName) {
        this.tabs.forEach(tab => {
            tab.classList.toggle('active', tab.dataset.pane === paneName);
        });
        this.inspector.querySelectorAll('.hub-tab-pane').forEach(pane => {
            pane.classList.toggle('active', pane.id.includes(paneName));
        });
    }
}
