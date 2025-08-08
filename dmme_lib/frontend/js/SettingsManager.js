// dmme_lib/frontend/js/SettingsManager.js
import { apiCall } from './wizards/ApiHelper.js';
import { status, confirmationModal } from './ui.js';

export class SettingsManager {
    constructor(appInstance) {
        this.app = appInstance;
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
        this.textModelsDatalist = document.getElementById('ollama-text-models-list');
        this.visionModelsDatalist = document.getElementById('ollama-vision-models-list');
        this.embeddingModelsDatalist = document.getElementById('ollama-embedding-models-list');
        this.kbDatalist = document.getElementById('kb-list');
    }

    _addEventListeners() {
        this.closeBtn.addEventListener('click', () => this.close());
        this.cancelBtn.addEventListener('click', () => this.close());
        this.saveBtn.addEventListener('click', () => this.saveSettings());
        this.tabs.forEach(tab => {
            tab.addEventListener('click', (e) => this._switchPane(e));
        });
    }

    async open() {
        this.modal.style.display = 'flex';
        this.overlay.style.display = 'block';
        await this.loadSettings();
        await this._populateModelSuggestions();
        await this._populateKbSuggestions();
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
            this.textModelsDatalist.innerHTML = '';
            this.visionModelsDatalist.innerHTML = '';
            this.embeddingModelsDatalist.innerHTML = '';

            models.forEach(model => {
                const option = document.createElement('option');
                option.value = model.name;

                switch (model.type_hint) {
                    case 'vision':
                        this.visionModelsDatalist.appendChild(option);
                        break;
                    case 'embedding':
                        this.embeddingModelsDatalist.appendChild(option);
                        break;
                    case 'text':
                    default:
                        this.textModelsDatalist.appendChild(option);
                        break;
                }
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

    async saveSettings() {
        this.statusEl.textContent = this.app.i18n.t('imageSaveStatusSaving');
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
        this.app.i18n.setLanguage(this.app.settings.Appearance.language);
        this.statusEl.textContent = this.app.i18n.t('settingsSaveStatus');
        setTimeout(() => this.close(), 1000);
    }

    applyTheme(themeName) {
        document.body.className = '';
        if (themeName && themeName !== 'default') {
            document.body.classList.add(`theme-${themeName}`);
        }
    }
}
