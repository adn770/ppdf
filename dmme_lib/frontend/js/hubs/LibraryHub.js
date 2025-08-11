// --- dmme_lib/frontend/js/hubs/LibraryHub.js ---
import { apiCall } from '../wizards/ApiHelper.js';
import { status, confirmationModal } from '../ui.js';

export class LibraryHub {
    constructor(appInstance, lightboxInstance) {
        this.app = appInstance;
        this.lightbox = lightboxInstance;
        this.isInitialized = false;
        this.selectedKb = null;
        this.selectedEntity = null;
        this.contentViewMode = 'list'; // 'list' or 'flow'
        this.kbDataCache = {};
        this.searchDebounceTimer = null;
    }

    _setupElements() {
        this.view = document.getElementById('library-view');
        this.tooltip = document.getElementById('data-tooltip');
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
        this.contentViewToggleBtn = document.getElementById('content-view-toggle-btn');
        this.contentFilterStatus = document.getElementById('content-filter-status');
        this.filterStatusTerm = document.getElementById('filter-status-term');
        this.clearContentFilterBtn = document.getElementById('clear-content-filter-btn');
        this.contentListEl = document.getElementById('content-explorer-list');

        this.entitiesView = document.getElementById('library-entities-view');
        this.entityListHeader = document.getElementById('entity-list-header');
        this.entityListKbNameEl = document.getElementById('entity-list-kb-name');
        this.entityFilterInput = document.getElementById('entity-filter-input');
        this.entityMasterList = document.getElementById('entity-master-list');
        this.entityDetailsPlaceholder = document.getElementById('entity-details-placeholder');
        this.entityRelatedChunks = document.getElementById('entity-related-chunks');

        this.assetsView = document.getElementById('library-assets-view');
        this.assetGrid = document.getElementById('asset-grid-container');
        this.dropzone = document.getElementById('asset-upload-dropzone');

        this.mindmapView = document.getElementById('library-mindmap-view');
        this.mindmapContainer = document.getElementById('mindmap-container');

        this.searchResultsView = document.getElementById('library-search-results-view');
        this.searchInput = document.getElementById('library-search-input');
        this.searchScope = document.getElementById('library-search-scope');
    }

    init() {
        if (this.isInitialized) return;
        this._setupElements();
        this.loadKnowledgeBases();
        this.tabs.forEach(tab => {
            tab.addEventListener('click', (e) => this._handleTabClick(e));
        });
        this._addDragDropListeners();
        this.listEl.addEventListener('click', (e) => this._handleKbListInteraction(e));
        this.assetGrid.addEventListener('click', (e) => this._handleAssetInteraction(e));
        this.entityFilterInput.addEventListener('input', () => this._filterEntityList());
        this.entityMasterList.addEventListener('click', (e) => this._handleEntitySelection(e));
        this.searchInput.addEventListener('input', () => this._debounceSearch());
        this.searchScope.addEventListener('change', () => this._performSearch());
        this.contentViewToggleBtn.addEventListener('click', () => this._toggleContentView());
        this._addTooltipListeners();
        // Delegated listener for clicks inside content areas
        const contentAreas = [this.contentListEl, this.searchResultsView, this.entityRelatedChunks];
        contentAreas.forEach(area => {
            area.addEventListener('click', (e) => this._handleContentAreaClick(e));
        });
        this.clearContentFilterBtn.addEventListener('click', () => this._clearContentFilter());

        this.isInitialized = true;
    }

    _addTooltipListeners() {
        const inspectorContent = this.inspector.querySelector('.hub-tab-content');
        const searchContent = this.searchResultsView;

        [inspectorContent, searchContent].forEach(el => {
            el.addEventListener('mouseover', (e) => this._handleTooltipShow(e));
            el.addEventListener('mouseout', (e) => this._handleTooltipHide(e));
            el.addEventListener('mousemove', (e) => this._updateTooltipPosition(e));
        });
    }

    _handleTooltipShow(event) {
        const statsTarget = event.target.closest('[data-structured-stats]');
        const linksTarget = event.target.closest('[data-linked-chunks]');
        if (!statsTarget && !linksTarget) return;

        let tooltipContent = '';
        try {
            if (statsTarget) {
                const statsRaw = statsTarget.dataset.structuredStats;
                const statsObj = JSON.parse(statsRaw);
                tooltipContent = JSON.stringify(statsObj, null, 2);
            } else if (linksTarget) {
                const linksRaw = linksTarget.dataset.linkedChunks;
                const linkIds = JSON.parse(linksRaw);
                const allDocs = this.kbDataCache[this.selectedKb.name]?.explore?.documents || [];
                const linkedTitles = linkIds.map(id => {
                    const doc = allDocs.find(d => d.chunk_id === id);
                    return doc ? doc.section_title : 'Unknown Section';
                });
                tooltipContent = `Linked Sections:\n- ${[...new Set(linkedTitles)].join('\n- ')}`;
            }
            this.tooltip.querySelector('pre').textContent = tooltipContent;
            this.tooltip.style.display = 'block';
            this._updateTooltipPosition(event);
        } catch (e) {
            console.error("Failed to parse tooltip JSON:", e);
            this.tooltip.querySelector('pre').textContent = "Error: Invalid data.";
            this.tooltip.style.display = 'block';
        }
    }

    _handleTooltipHide(event) {
        const target = event.target.closest('[data-structured-stats], [data-linked-chunks]');
        if (target && this.tooltip) {
            this.tooltip.style.display = 'none';
        }
    }

    _updateTooltipPosition(event) {
        if (!this.tooltip || this.tooltip.style.display !== 'block') return;
        const offsetX = 15;
        const offsetY = 15;
        const tooltipRect = this.tooltip.getBoundingClientRect();
        const viewportWidth = window.innerWidth;
        const viewportHeight = window.innerHeight;
        let top = event.clientY + offsetY;
        let left = event.clientX + offsetX;
        if (left + tooltipRect.width > viewportWidth) {
            left = event.clientX - tooltipRect.width - offsetX;
        }
        if (top + tooltipRect.height > viewportHeight) {
            top = event.clientY - tooltipRect.height - offsetY;
        }
        if (left < 0) left = offsetX;
        if (top < 0) top = offsetY;

        this.tooltip.style.left = `${left}px`;
        this.tooltip.style.top = `${top}px`;
    }

    async _handleContentAreaClick(event) {
        const breadcrumb = event.target.closest('[data-action="breadcrumb-search"]');
        const tagChip = event.target.closest('.tag-chip');
        const expandBtn = event.target.closest('.chunk-expand-btn');

        if (breadcrumb) {
            this._handleBreadcrumbClick(breadcrumb);
        } else if (tagChip) {
            this._handleTagClick(tagChip);
        } else if (expandBtn) {
            await this._handleProgressiveReveal(expandBtn);
        }
    }

    _handleBreadcrumbClick(breadcrumbElement) {
        const sectionTitle = breadcrumbElement.dataset.sectionQuery;
        this.contentFilterStatus.style.display = 'flex';
        this.filterStatusTerm.textContent = sectionTitle;
        this.switchTab('content');
        this.contentListEl.querySelectorAll('.text-chunk-card').forEach(card => {
            const cardSection = card.querySelector('.breadcrumb-link')?.dataset.sectionQuery;
            card.style.display = (cardSection === sectionTitle) ? 'flex' : 'none';
        });
    }

    _handleTagClick(tagChipElement) {
        const tag = tagChipElement.textContent;
        // Switch to content view if not already there
        this.switchTab('content');
        this._applyTagFilter(tag);
    }

    async _handleProgressiveReveal(button) {
        const card = button.closest('.text-chunk-card');
        const chunkId = card.dataset.chunkId;
        const contentEl = card.querySelector('.text-chunk-content');
        const summaryText = card.dataset.summary;
        if (card.classList.contains('is-expanded')) {
            // Collapse
            contentEl.innerHTML = window.marked.parse(summaryText || '');
            button.textContent = '[ ▾ Expand ]';
            card.classList.remove('is-expanded');
        } else {
            // Expand
            button.textContent = '[...]';
            try {
                const chunk = await apiCall(
                    `/api/knowledge/chunk/${this.selectedKb.name}/${chunkId}`
                );
                contentEl.innerHTML = window.marked.parse(chunk.document);
                button.textContent = '[ ▴ Collapse ]';
                card.classList.add('is-expanded');
            } catch (error) {
                contentEl.textContent = 'Error loading full text.';
                button.textContent = '[ ▾ Expand ]';
            }
        }
    }

    _applyTagFilter(tag) {
        this.contentFilterStatus.style.display = 'flex';
        this.filterStatusTerm.textContent = tag;
        const cardElements = this.contentListEl.querySelectorAll('.text-chunk-card');
        cardElements.forEach(card => {
            try {
                const cardTags = JSON.parse(card.dataset.tags || '[]');
                card.style.display = cardTags.includes(tag) ? 'flex' : 'none';
            } catch (e) {
                card.style.display = 'none';
            }
        });
    }

    _clearContentFilter() {
        this.contentFilterStatus.style.display = 'none';
        this.contentListEl.querySelectorAll('.text-chunk-card').forEach(card => {
            card.style.display = 'flex';
        });
    }

    _debounceSearch() {
        clearTimeout(this.searchDebounceTimer);
        this.searchDebounceTimer = setTimeout(() => this._performSearch(), 300);
    }

    async _performSearch() {
        const query = this.searchInput.value.trim();
        const scope = this.searchScope.value;

        if (!query) {
            this._showInspector();
            this._clearContentFilter();
            return;
        }

        this._showSearchResults();
        this.searchResultsView.innerHTML = '<div class="spinner"></div>';
        try {
            const results = await apiCall(`/api/search?q=${encodeURIComponent(query)}&scope=${scope}`);
            this._renderSearchResults(results);
        } catch (error) {
            this.searchResultsView.innerHTML = '<p class="error">Search failed.</p>';
        }
    }

    _renderSearchResults(results) {
        this.searchResultsView.innerHTML = '';
        if (!results || results.length === 0) {
            this.searchResultsView.innerHTML = `<p>No results for "${this.searchInput.value}".</p>`;
            return;
        }
        results.forEach(result => {
            const cardHtml = this._createChunkCardHTML(result, true);
            this.searchResultsView.insertAdjacentHTML('beforeend', cardHtml);
        });
    }

    _showInspector() {
        this.searchResultsView.style.display = 'none';
        if (this.selectedKb) {
            this.inspector.style.display = 'block';
            this.content.style.display = 'flex';
            this.placeholder.style.display = 'none';
        } else {
            this.inspector.style.display = 'block';
            this.content.style.display = 'none';
            this.placeholder.style.display = 'flex';
        }
    }

    _showSearchResults() {
        this.content.style.display = 'none';
        this.placeholder.style.display = 'none';
        this.searchResultsView.style.display = 'flex';
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
        if (this.selectedKb?.name === kb.name && !this.searchInput.value.trim()) return;
        this.selectedKb = kb;
        this.selectedEntity = null;
        this.contentViewMode = 'list';
        this.kbDataCache[kb.name] = {};
        this._updateSearchScope();
        if (this.searchInput.value.trim()) {
            this._performSearch();
        } else {
            this._showInspector();
        }

        this.listEl.querySelectorAll('li').forEach(li => {
            li.classList.toggle('selected', li.dataset.kbName === kb.name);
        });
        this._clearContentFilter();
        this.switchTab('dashboard');
        this.renderDashboard();
        this._loadAndRenderEntityList();
        this._getKbExploreData(); // Proactively fetch and cache all document data
    }

    _updateSearchScope() {
        this.searchScope.innerHTML = '<option value="all">All Knowledge</option>';
        if (this.selectedKb) {
            const option = document.createElement('option');
            option.value = this.selectedKb.name;
            option.textContent = `Current: ${this.selectedKb.name}`;
            this.searchScope.appendChild(option);
            this.searchScope.value = this.selectedKb.name;
        }
    }

    async renderDashboard() {
        this.chunkCountEl.textContent = '...';
        this.entityChartEl.innerHTML = '<div class="spinner"></div>';
        this.wordCloudEl.innerHTML = '<div class="spinner"></div>';
        try {
            const data = await apiCall(`/api/knowledge/dashboard/${this.selectedKb.name}`);
            this.kbDataCache[this.selectedKb.name].dashboard = data;
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
            const fontSize = 0.8 + weight * 1.2;
            span.style.fontSize = `${fontSize}rem`;
            this.wordCloudEl.appendChild(span);
        });
    }

    async renderContentView() {
        this._updateContentViewToggle();
        this._clearContentFilter();
        const wrapper = this.contentListEl;
        wrapper.innerHTML = '<div class="spinner"></div>';
        const data = await this._getKbExploreData();
        const isDeep = this.selectedKb.metadata?.indexing_strategy === 'deep';

        const summaryMap = new Map();
        if (isDeep && data.summaries) {
            data.summaries.forEach(summary => {
                summaryMap.set(summary.parent_id, summary.document);
            });
        }
        this.kbDataCache[this.selectedKb.name].content = data.documents;
        wrapper.innerHTML = '';
        if (!data.documents || data.documents.length === 0) {
            wrapper.innerHTML = `<p>No text documents found in this knowledge base.</p>`;
            return;
        }

        if (this.contentViewMode === 'list') {
            data.documents.forEach(doc => {
                const summary = isDeep ? summaryMap.get(doc.chunk_id) : null;
                wrapper.insertAdjacentHTML('beforeend', this._createChunkCardHTML(doc, false, summary));
            });
        } else { // 'flow' mode
            const sections = data.documents.reduce((acc, doc) => {
                const title = doc.section_title || 'Uncategorized';
                if (!acc[title]) {
                    acc[title] = { page: doc.page_start || 0, chunks: [] };
                }
                acc[title].chunks.push(doc);
                return acc;
            }, {});
            const sortedSections = Object.entries(sections).sort((a, b) => a[1].page - b[1].page);

            for (const [title, sectionData] of sortedSections) {
                const header = document.createElement('h4');
                header.className = 'section-flow-header';
                header.textContent = title;
                wrapper.appendChild(header);
                sectionData.chunks.forEach(doc => {
                    const summary = isDeep ? summaryMap.get(doc.chunk_id) : null;
                    wrapper.insertAdjacentHTML('beforeend', this._createChunkCardHTML(doc, false, summary));
                });
            }
        }
    }

    async _loadAndRenderEntityList() {
        this.entityListKbNameEl.textContent = `'${this.selectedKb.name}'`;
        this.entityMasterList.innerHTML = '<div class="spinner"></div>';
        const entities = await this._getKbEntityData();
        this.entityMasterList.innerHTML = '';
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
            if (!li.dataset.entityName) return;
            const name = li.dataset.entityName.toLowerCase();
            li.style.display = name.includes(filter) ? '' : 'none';
        });
    }

    async _handleEntitySelection(event) {
        const li = event.target.closest('li[data-entity-name]');
        if (!li) return;

        this.searchInput.value = '';
        this.selectedEntity = li.dataset.entityName;
        this.entityMasterList.querySelectorAll('li').forEach(el => el.classList.remove('selected'));
        li.classList.add('selected');

        this.entityRelatedChunks.innerHTML = '<div class="spinner"></div>';
        this.switchTab('entities');
        const data = await this._getKbExploreData();
        if (!data.documents) return;

        const relatedChunks = data.documents.filter(doc => {
            try {
                const entities = JSON.parse(doc.entities || '{}');
                return Object.keys(entities).includes(this.selectedEntity);
            } catch (e) { return false; }
        });
        this.entityRelatedChunks.innerHTML = '';
        if (relatedChunks.length === 0) {
            this.entityRelatedChunks.innerHTML = `<p>No chunks for "${this.selectedEntity}".</p>`;
        } else {
            relatedChunks.forEach(doc => {
                this.entityRelatedChunks.insertAdjacentHTML('beforeend', this._createChunkCardHTML(doc));
            });
        }
    }

    _createChunkCardHTML(result, isSearchResult = false, summaryText = null) {
        const doc = isSearchResult ?
            { ...result.metadata, document: result.document } : result;
        const kbName = isSearchResult ? result.kb_name : this.selectedKb.name;
        const tags = JSON.parse(doc.tags || '[]');
        const tagsForAttr = doc.tags || '[]';
        const tagsHTML = tags.map(tag => {
            const [category] = tag.split(':', 1);
            return `<span class="tag-chip tag-category--${category}">${tag}</span>`;
        }).join('');
        const keyTerms = JSON.parse(doc.key_terms || '[]');
        const keyTermsHTML = keyTerms.map(term => `<span class="key-term-chip">${term}</span>`).join('');
        const linksStr = doc.linked_chunks || '[]';
        const hasLinks = JSON.parse(linksStr).length > 0;
        const statsStr = doc.structured_stats || doc.structured_spell_data || '{}';
        const hasStats = statsStr && statsStr !== '{}';
        const sectionTitle = doc.section_title || 'Untitled Section';
        const sourceInfo = isSearchResult ?
            `<span class="search-result-score">Score: ${result.distance.toFixed(2)}</span>` :
            `<span>p. ${doc.page_start || 'N/A'}</span>`;
        const escapedStatsStr = statsStr.replace(/'/g, "&apos;");
        const statsAttr = hasStats ? `data-structured-stats='${escapedStatsStr}'` : '';
        const linksAttr = hasLinks ? `data-linked-chunks='${linksStr}'` : '';
        const content = summaryText ? summaryText : doc.document;
        const expandButton = summaryText ? `<button class="chunk-expand-btn">[ ▾ Expand ]</button>` : '';
        return `
        <div class="text-chunk-card" data-chunk-id="${doc.chunk_id}"
             data-summary="${summaryText ?
            summaryText.replace(/"/g, '&quot;') : ''}" data-tags='${tagsForAttr}'>
            <div class="chunk-breadcrumb">
                <span>${kbName} > </span>
                <span class="breadcrumb-link"
                    data-action="breadcrumb-search"
                      data-kb-scope="${kbName}"
                      data-section-query="${sectionTitle}">
                    ${sectionTitle}
                </span>
            </div>
            <div class="text-chunk-header">
                <div class="tag-list">${tagsHTML}</div>
                <div>${sourceInfo}</div>
            </div>
            <div class="text-chunk-content">${window.marked.parse(content)}</div>
            <div class="text-chunk-footer">
                <div class="key-terms-list">${keyTermsHTML}</div>
                <div class="metadata-icons">
                    ${expandButton}
                    ${hasLinks ?
            `<span title="Show linked sections" ${linksAttr}>🔗</span>` : ''}
                    ${hasStats ?
            `<span title="Show structured data" ${statsAttr}>{}</span>` : ''}
                </div>
            </div>
        </div>`;
    }

    async renderAssetsView() {
        this._clearContentFilter();
        this.assetGrid.innerHTML = '<div class="spinner"></div>';
        const data = await this._getKbExploreData();
        this.kbDataCache[this.selectedKb.name].assets = data.assets;
        this.assetGrid.innerHTML = '';
        if (!data.assets || data.assets.length === 0) {
            this.assetGrid.innerHTML = `<p>${this.app.i18n.t('noAssetsFound')}</p>`;
            return;
        }
        data.assets.forEach(asset => this._addAssetToGrid(asset, false));
    }

    async _getKbExploreData() {
        const cacheKey = this.selectedKb.name;
        if (!this.kbDataCache[cacheKey]?.explore) {
            this.kbDataCache[cacheKey].explore = await apiCall(`/api/knowledge/explore/${cacheKey}`);
        }
        return this.kbDataCache[cacheKey].explore;
    }

    async _getKbEntityData() {
        const cacheKey = this.selectedKb.name;
        if (!this.kbDataCache[cacheKey]?.entities) {
            this.kbDataCache[cacheKey].entities = await apiCall(`/api/knowledge/entities/${cacheKey}`);
        }
        return this.kbDataCache[cacheKey].entities;
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
                    this.searchResultsView.style.display = 'none';
                    this.selectedKb = null;
                    this.entityMasterList.innerHTML = '';
                    this.entityListKbNameEl.textContent = '';
                    this._updateSearchScope();
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

    _handleTabClick(event) {
        const paneName = event.target.dataset.pane;
        this.switchTab(paneName);

        if (this.selectedKb) {
            const kbName = this.selectedKb.name;
            const cache = this.kbDataCache[kbName];

            if (paneName === 'content' && !cache.content) {
                this.renderContentView();
            } else if (paneName === 'assets' && !cache.assets) {
                this.renderAssetsView();
            } else if (paneName === 'mindmap' && !cache.mindmap) {
                this.renderMindMapView();
            }
        }
    }

    switchTab(paneName) {
        if (this.searchInput.value.trim()) {
            this._showSearchResults();
            return;
        } else {
            this._showInspector();
        }

        this.tabs.forEach(tab => {
            tab.classList.toggle('active', tab.dataset.pane === paneName);
        });
        this.panes.forEach(pane => {
            const paneId = `library-${paneName}-view`;
            pane.classList.toggle('active', pane.id === paneId);
        });
        if (this.selectedKb && paneName === 'entities') {
            if (this.selectedEntity) {
                this.entityDetailsPlaceholder.style.display = 'none';
                this.entityRelatedChunks.style.display = 'flex';
            } else {
                this.entityDetailsPlaceholder.style.display = 'flex';
                this.entityRelatedChunks.style.display = 'none';
            }
        }
    }

    _toggleContentView() {
        this.contentViewMode = this.contentViewMode === 'list' ?
            'flow' : 'list';
        this.renderContentView();
    }

    _updateContentViewToggle() {
        const isFlow = this.contentViewMode === 'flow';
        this.contentViewToggleBtn.title = isFlow ? 'Switch to List View' : 'Switch to Section Flow View';
        this.contentViewToggleBtn.innerHTML = isFlow ?
            `<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="8" x2="21" y1="6" y2="6"></line><line x1="8" x2="21" y1="12" y2="12"></line><line x1="8" x2="21" y1="18" y2="18"></line><line x1="3" x2="3.01" y1="6" y2="6"></line><line x1="3" x2="3.01" y1="12" y2="12"></line><line x1="3" x2="3.01" y1="18" y2="18"></line></svg>` :
            `<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="6" rx="2"></rect><path d="M3 11h18M3 19h18"></path></svg>`;
    }

    async renderMindMapView() {
        this.mindmapContainer.innerHTML = '<div class="spinner"></div>';
        const data = await this._getKbExploreData();
        this.kbDataCache[this.selectedKb.name].mindmap = true; // Mark as loaded

        if ((!data.documents || data.documents.length === 0) && (!data.summaries || data.summaries.length === 0)) {
            this.mindmapContainer.innerHTML = '<p>No content to generate a mind map.</p>';
            return;
        }

        const { nodes, links } = this._buildGraphData(data);
        const mermaidSyntax = this._generateMermaidSyntax(nodes, links);

        try {
            const { svg } = await mermaid.render('mindmap-svg', mermaidSyntax);
            this.mindmapContainer.innerHTML = svg;

            const svgElement = this.mindmapContainer.querySelector('svg');
            if (svgElement) {
                svgPanZoom(svgElement, {
                    zoomEnabled: true,
                    controlIconsEnabled: true,
                    fit: true,
                    center: true,
                    minZoom: 0.1,
                    maxZoom: 10,
                });
            }
        } catch (e) {
            this.mindmapContainer.innerHTML = '<p class="error">Error rendering mind map.</p>';
            console.error("Mermaid rendering error:", e);
        }
    }

    _buildGraphData(data) {
        const isDeep = this.selectedKb.metadata?.indexing_strategy === 'deep';
        const documents = (isDeep && data.summaries) ? data.summaries : data.documents;
        const sections = {};
        const entityToSections = {};
        documents.forEach(doc => {
            const title = doc.section_title || 'Uncategorized';
            if (!sections[title]) {
                sections[title] = { id: `s${Object.keys(sections).length}`, page: doc.page_start || 0 };
            }
            try {
                const entities = JSON.parse(doc.entities || '{}');
                for (const entityName of Object.keys(entities)) {
                    if (!entityToSections[entityName]) entityToSections[entityName] = new Set();
                    entityToSections[entityName].add(title);
                }
            } catch (e) { /* ignore */ }
        });
        const nodes = Object.entries(sections).sort((a, b) => a[1].page - b[1].page);
        const links = new Set();
        for (const entity in entityToSections) {
            const connectedSections = Array.from(entityToSections[entity]);
            if (connectedSections.length > 1) {
                for (let i = 0; i < connectedSections.length; i++) {
                    for (let j = i + 1; j < connectedSections.length; j++) {
                        const s1 = sections[connectedSections[i]].id;
                        const s2 = sections[connectedSections[j]].id;
                        links.add(`${s1} -- "${entity}" --> ${s2}`);
                    }
                }
            }
        }
        return { nodes, links };
    }

    _generateMermaidSyntax(nodes, links) {
        let syntax = 'graph TD;\n';
        nodes.forEach(([title, data], index) => {
            const safeTitle = title.replace(/"/g, '#quot;');
            syntax += `    ${data.id}["${safeTitle}"];\n`;
            if (index > 0) {
                const prevId = nodes[index - 1][1].id;
                syntax += `    ${prevId} --> ${data.id};\n`;
            }
        });
        links.forEach(link => {
            syntax += `    ${link};\n`;
        });
        return syntax;
    }
}
