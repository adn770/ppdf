// dmme_lib/frontend/js/SettingsManager.js
import { apiCall } from './wizards/ApiHelper.js';
import { status, confirmationModal } from './ui.js';

export class SettingsManager {
    constructor(appInstance) {
        this.app = appInstance; // Store a reference to the main app
        this.settings = null;

        this._setupElements();
        this._addEventListeners();
    }

    _setupElements() {
        this.modal = document.getElementById('settings-modal');
        this.overlay = document.getElementById('modal-overlay');
        this.closeBtn = this.modal.querySelector('.close-btn');
        this.cancelBtn = document.getElementById('settings-cancel-btn');
        this.saveBtn = document.getElementById('settings-save-btn');
        this.statusEl = document.getElementById('settings-save-status');
        this.tabs = this.modal.querySelectorAll('.wizard-tab-btn');
        this.panes = this.modal.querySelectorAll('.settings-pane');
        this.inputs = this.modal.querySelectorAll('[data-section][data-key]');
        this.modelsDatalist = document.getElementById('ollama-models-list');
        this.kbDatalist = document.getElementById('kb-list');
        this.ragStatusContainer = document.getElementById('rag-status-container');
    }

    _addEventListeners() {
        this.closeBtn.addEventListener('click', () => this.close());
        this.cancelBtn.addEventListener('click', () => this.close());
        this.saveBtn.addEventListener('click', () => this.saveSettings());
        this.tabs.forEach(tab => {
            tab.addEventListener('click', (e) => this._switchPane(e));
        });
        this.ragStatusContainer.addEventListener('click', (e) => this._handleRagActions(e));
    }

    async open() {
        this.modal.style.display = 'flex';
        this.overlay.style.display = 'block';
        await this.loadSettings();
        await this._populateModelSuggestions();
        await this._populateKbSuggestions();
        await this._loadRagStatus();
    }

    close() {
        this.modal.style.display = 'none';
        this.overlay.style.display = 'none';
        this.statusEl.textContent = '';
    }

    _switchPane(event) {
        event.preventDefault();
        const targetPaneId = event.target.dataset.pane;
        this.tabs.forEach(tab => {
            tab.classList.toggle('active', tab.dataset.pane === targetPaneId);
        });
        this.panes.forEach(pane => {
            pane.classList.toggle('active', pane.id === `pane-${targetPaneId}`);
        });
    }

    async loadSettings() {
        this.settings = await apiCall('/api/settings/');
        this.inputs.forEach(input => {
            const section = input.dataset.section;
            const key = input.dataset.key;
            if (this.settings[section] && this.settings[section][key] !== undefined) {
                input.value = this.settings[section][key];
            }
        });
        return this.settings;
    }

    async _populateModelSuggestions() {
        try {
            const models = await apiCall('/api/ollama/models');
            this.modelsDatalist.innerHTML = '';
            models.forEach(modelName => {
                const option = document.createElement('option');
                option.value = modelName;
                this.modelsDatalist.appendChild(option);
            });
        } catch (error) {
            console.error("Failed to populate Ollama model suggestions:", error);
        }
    }

    async _populateKbSuggestions() {
        try {
            const kbs = await apiCall('/api/knowledge/');
            this.kbDatalist.innerHTML = '';
            kbs.forEach(kb => {
                const option = document.createElement('option');
                option.value = kb.name;
                this.kbDatalist.appendChild(option);
            });
        } catch (error) {
            console.error("Failed to populate knowledge base suggestions:", error);
        }
    }

    async _loadRagStatus() {
        this.ragStatusContainer.innerHTML = '<p>Loading knowledge bases...</p>';
        try {
            const kbs = await apiCall('/api/knowledge/');
            this._renderRagStatus(kbs);
        } catch (error) {
            this.ragStatusContainer.innerHTML =
                '<p class="error">Failed to load knowledge bases.</p>';
        }
    }

    _renderRagStatus(kbs) {
        if (kbs.length === 0) {
            this.ragStatusContainer.innerHTML = '<p>No knowledge bases have been created yet.</p>';
            return;
        }

        const allMetaKeys = new Set();
        kbs.forEach(kb => Object.keys(kb.metadata).forEach(key => allMetaKeys.add(key)));
        
        // Define a preferred order, but still be dynamic
        const preferredOrder = ['kb_type', 'language', 'filename'];
        const sortedMetaKeys = preferredOrder.filter(k => allMetaKeys.has(k));
        allMetaKeys.forEach(k => {
            if (!preferredOrder.includes(k) && k !== 'description') {
                sortedMetaKeys.push(k);
            }
        });

        const headers = ['Name', ...sortedMetaKeys, 'Documents'];
        
        const table = document.createElement('table');
        table.className = 'info-table';
        const thead = document.createElement('thead');
        thead.innerHTML = `<tr>${headers.map(h => `<th>${h.replace('kb_','')}</th>`).join('')}<th></th></tr>`;
        
        const tbody = document.createElement('tbody');
        kbs.forEach(kb => {
            const row = document.createElement('tr');
            row.title = kb.metadata?.description || 'No description provided.';

            let cells = `<td>${kb.name}</td>`;
            sortedMetaKeys.forEach(key => {
                cells += `<td>${kb.metadata[key] || 'N/A'}</td>`;
            });
            cells += `<td>${kb.count}</td>`;
            cells += `<td class="actions-cell"><button class="delete-icon-btn" data-kb-name="${kb.name}">🗑️</button></td>`;
            row.innerHTML = cells;
            tbody.appendChild(row);
        });

        table.appendChild(thead);
        table.appendChild(tbody);
        this.ragStatusContainer.innerHTML = '';
        this.ragStatusContainer.appendChild(table);
    }

    async _handleRagActions(event) {
        const deleteBtn = event.target.closest('.delete-icon-btn');
        if (!deleteBtn) return;

        const kbName = deleteBtn.dataset.kbName;
        const confirmed = await confirmationModal.confirm(
            'Delete Knowledge Base',
            `Are you sure you want to permanently delete the '${kbName}' knowledge base?`
        );

        if (confirmed) {
            try {
                await apiCall(`/api/knowledge/${kbName}`, { method: 'DELETE' });
                status.setText(`Knowledge base '${kbName}' deleted.`);
                await this._loadRagStatus(); // Refresh the list
            } catch (error) {
                // The apiCall helper already shows a status bar error
            }
        }
    }

    async saveSettings() {
        this.statusEl.textContent = 'Saving...';
        const newSettings = {
            Appearance: {},
            Ollama: {},
            Game: {}
        };
        this.inputs.forEach(input => {
            const section = input.dataset.section;
            const key = input.dataset.key;
            if (!newSettings[section]) {
                newSettings[section] = {};
            }
            newSettings[section][key] = input.value;
        });
        await apiCall('/api/settings/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(newSettings),
        });
        this.app.settings = newSettings; // Update the global app settings
        this.applyTheme(this.app.settings.Appearance.theme);
        this.statusEl.textContent = 'Saved!';
        setTimeout(() => this.close(), 1000);
    }

    applyTheme(themeName) {
        document.body.className = ''; // Clear existing themes
        if (themeName && themeName !== 'default') {
            document.body.classList.add(`theme-${themeName}`);
        }
    }
}
