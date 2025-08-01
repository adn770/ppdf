// dmme_lib/frontend/js/SettingsManager.js
import { apiCall } from './wizards/ApiHelper.js';
export class SettingsManager {
    constructor() {
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
        const table = document.createElement('table');
        table.className = 'rag-status-table';
        table.innerHTML = `
            <thead>
                <tr>
                    <th>Name</th>
                    <th>Documents</th>
                    <th>Actions</th>
                </tr>
            </thead>
        `;
        const tbody = document.createElement('tbody');
        kbs.forEach(kb => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${kb.name}</td>
                <td>${kb.count}</td>
                <td>
                    <button class="danger-btn clear-rag-btn" data-kb-name="${kb.name}">
                        Clear
                    </button>
                </td>
            `;
            tbody.appendChild(row);
        });
        table.appendChild(tbody);
        this.ragStatusContainer.innerHTML = '';
        this.ragStatusContainer.appendChild(table);
    }

    async _handleRagActions(event) {
        const clearBtn = event.target.closest('.clear-rag-btn');
        if (!clearBtn) return;

        const kbName = clearBtn.dataset.kbName;
        const msg = `Are you sure you want to permanently delete the '${kbName}' knowledge base?`;
        if (confirm(msg)) {
            try {
                await apiCall(`/api/knowledge/${kbName}`, { method: 'DELETE' });
                await this._loadRagStatus(); // Refresh the list
            } catch (error) {
                // The apiCall helper already shows an alert
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
        this.settings = newSettings;
        this.applyTheme(this.settings.Appearance.theme);
        this.statusEl.textContent = 'Saved!';
        setTimeout(() => this.statusEl.textContent = '', 2000);
    }

    applyTheme(themeName) {
        document.body.className = ''; // Clear existing themes
        if (themeName && themeName !== 'default') {
            document.body.classList.add(`theme-${themeName}`);
        }
    }
}
