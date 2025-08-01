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
        this.navLinks = this.modal.querySelectorAll('.settings-nav a');
        this.panes = this.modal.querySelectorAll('.settings-pane');
        this.inputs = this.modal.querySelectorAll('[data-section][data-key]');
    }

    _addEventListeners() {
        this.closeBtn.addEventListener('click', () => this.close());
        this.cancelBtn.addEventListener('click', () => this.close());
        this.saveBtn.addEventListener('click', () => this.saveSettings());
        this.navLinks.forEach(link => {
            link.addEventListener('click', (e) => this._switchPane(e));
        });
    }

    async open() {
        this.modal.style.display = 'flex';
        this.overlay.style.display = 'block';
        await this._loadSettings();
    }

    close() {
        this.modal.style.display = 'none';
        this.overlay.style.display = 'none';
        this.statusEl.textContent = '';
    }

    _switchPane(event) {
        event.preventDefault();
        const targetPaneId = event.target.dataset.pane;
        this.navLinks.forEach(link => {
            link.classList.toggle('active', link.dataset.pane === targetPaneId);
        });
        this.panes.forEach(pane => {
            pane.classList.toggle('active', pane.id === `pane-${targetPaneId}`);
        });
    }

    async _loadSettings() {
        this.settings = await apiCall('/api/settings/');
        this.inputs.forEach(input => {
            const section = input.dataset.section;
            const key = input.dataset.key;
            if (this.settings[section] && this.settings[section][key]) {
                input.value = this.settings[section][key];
            }
        });
    }

    async saveSettings() {
        this.statusEl.textContent = 'Saving...';
        const newSettings = JSON.parse(JSON.stringify(this.settings));
        this.inputs.forEach(input => {
            const section = input.dataset.section;
            const key = input.dataset.key;
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

    async loadAndApplyTheme() {
        if (!this.settings) {
            this.settings = await apiCall('/api/settings/');
        }
        this.applyTheme(this.settings.Appearance.theme);
    }

    applyTheme(themeName) {
        document.body.className = ''; // Clear existing themes
        if (themeName !== 'default') {
            document.body.classList.add(`theme-${themeName}`);
        }
    }
}
