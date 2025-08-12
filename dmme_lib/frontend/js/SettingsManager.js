// dmme_lib/frontend/js/SettingsManager.js
import { apiCall } from './wizards/ApiHelper.js';
import { status } from './ui.js';

export class SettingsManager {
    constructor(appInstance) {
        this.app = appInstance;
        this.settings = null;
        this.saveDebounceTimer = null;

        this._setupElements();
        this._addEventListeners();
    }

    _setupElements() {
        this.modal = document.getElementById('settings-modal');
        this.overlay = document.getElementById('modal-overlay');
        this.closeBtn = this.modal.querySelector('.close-btn');
        this.statusEl = document.getElementById('settings-save-status');
        this.tabs = this.modal.querySelectorAll('.wizard-tab-btn');
        this.panes = this.modal.querySelectorAll('.settings-pane');

        // Datalists for suggestions
        this.textModelsDatalist = document.getElementById('ollama-text-models-list');
        this.visionModelsDatalist = document.getElementById('ollama-vision-models-list');
        this.embeddingModelsDatalist = document.getElementById('ollama-embedding-models-list');
        this.kbDatalist = document.getElementById('kb-list');
    }

    _addEventListeners() {
        this.closeBtn.addEventListener('click', () => this.close());
        this.tabs.forEach(tab => {
            tab.addEventListener('click', (e) => this._switchPane(e));
        });
        // Add listeners for sliders to update their displayed value
        this.modal.querySelectorAll('input[type="range"]').forEach(slider => {
            const valueEl = slider.nextElementSibling;
            if (valueEl && valueEl.classList.contains('slider-value')) {
                slider.addEventListener('input', () => {
                    valueEl.textContent = slider.value;
                });
            }
        });
        // Add a single delegated listener for any change in the settings content
        this.modal.querySelector('.settings-content').addEventListener('change', () => {
            this._debounceSave();
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
        // --- Simple Key-Value Sections ---
        ['Appearance', 'Game'].forEach(section => {
            const sectionSettings = this.settings[section] || {};
            for (const key in sectionSettings) {
                const input = this.modal.querySelector(
                    `[data-section="${section}"][data-key="${key}"]`
                );
                if (input) input.value = sectionSettings[key];
            }
        });
        // --- Complex, Role-Based LLM Sections ---
        ['OllamaGame', 'OllamaIngestion'].forEach(section => {
            const sectionSettings = this.settings[section] || {};
            const urlInput = this.modal.querySelector(`[data-section="${section}"][data-key="url"]`);
            if (urlInput) urlInput.value = sectionSettings.url || '';

            try {
                const models = JSON.parse(sectionSettings.models_json || '{}');
                for (const role in models) {
                    for (const key in models[role]) {
                        const input = this.modal.querySelector(
                            `[data-section="${section}"][data-role="${role}"][data-key="${key}"]`
                        );
                        if (input) {
                            input.value = models[role][key];
                            if (input.type === 'range') {
                                const valueEl = input.nextElementSibling;
                                if (valueEl) valueEl.textContent = models[role][key];
                            }
                        }
                    }
                }
            } catch (e) {
                console.error(`Failed to parse models_json for ${section}:`, e);
            }
        });

        return this.settings;
    }

    stopAutosave() {
        if (this.saveDebounceTimer) {
            clearTimeout(this.saveDebounceTimer);
            this.saveDebounceTimer = null;
        }
    }

    _debounceSave() {
        this.stopAutosave();
        console.trace("TRACE: SettingsManager autosave timer starting.");
        this.statusEl.textContent = this.app.i18n.t('savingStatus');
        this.saveDebounceTimer = setTimeout(() => this.saveSettings(), 500);
    }

    async saveSettings() {
        const newSettings = {};

        // --- Simple Key-Value Sections ---
        ['Appearance', 'Game'].forEach(section => {
            newSettings[section] = {};
            this.modal.querySelectorAll(`[data-section="${section}"]`).forEach(input => {
                newSettings[section][input.dataset.key] = input.value;
            });
        });
        // --- Complex, Role-Based LLM Sections ---
        ['OllamaGame', 'OllamaIngestion'].forEach(section => {
            newSettings[section] = {};
            const urlInput = this.modal.querySelector(`[data-section="${section}"][data-key="url"]`);
            newSettings[section].url = urlInput ? urlInput.value : '';

            const models = {};
            const roles = new Set(Array.from(
                this.modal.querySelectorAll(`[data-section="${section}"][data-role]`)
            ).map(el => el.dataset.role));

            roles.forEach(role => {
                models[role] = {};
                this.modal.querySelectorAll(
                    `[data-section="${section}"][data-role="${role}"]`
                ).forEach(input => {
                    models[role][input.dataset.key] = input.value;
                });
            });
            newSettings[section].models_json = JSON.stringify(models);
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
        setTimeout(() => { this.statusEl.textContent = ''; }, 2000);
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

    applyTheme(themeName) {
        document.body.className = '';
        if (themeName && themeName !== 'default') {
            document.body.classList.add(`theme-${themeName}`);
        }
    }
}
