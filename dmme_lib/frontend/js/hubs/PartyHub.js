// dmme_lib/frontend/js/hubs/PartyHub.js
import { apiCall } from '../wizards/ApiHelper.js';
import { status, confirmationModal } from '../ui.js';

export class PartyHub {
    constructor(appInstance) {
        this.app = appInstance;
        this.isInitialized = false;
        this.selectedPartyId = null;

        // Main containers
        this.view = document.getElementById('party-view');
        this.listEl = document.getElementById('party-list-hub');
        this.inspectorPlaceholder = document.getElementById('party-inspector-placeholder');
        this.inspectorContent = document.getElementById('party-inspector-content');
        this.rosterView = document.getElementById('party-roster-hub');
        this.editorView = document.getElementById('character-editor-hub');
        this.characterListEl = document.getElementById('character-list-hub');
        this.showAddCharacterBtn = document.getElementById('show-add-character-hub-btn');

        // Editor form inputs
        this.charNameInput = document.getElementById('char-name-hub');
        this.charClassInput = document.getElementById('char-class-hub');
        this.charLevelInput = document.getElementById('char-level-hub');
        this.aiDescInput = document.getElementById('ai-char-desc-hub');
        this.addManualBtn = document.getElementById('add-char-manual-hub-btn');
        this.aiGenerateBtn = document.getElementById('ai-char-generate-hub-btn');
    }

    init() {
        if (this.isInitialized) return;
        this.loadParties();
        this.showAddCharacterBtn.addEventListener('click', () => this.showEditorPanel());
        this.addManualBtn.addEventListener('click', () => this.addCharacter(false));
        this.aiGenerateBtn.addEventListener('click', () => this.addCharacter(true));
        this.characterListEl.addEventListener('click', (e) => this._handleCharacterDelete(e));
        this.isInitialized = true;
    }

    async loadParties() {
        this.listEl.innerHTML = `<li>${this.app.i18n.t('loadingParties')}</li>`;
        try {
            const parties = await apiCall('/api/parties/');
            this.renderPartyList(parties);
        } catch (error) {
            this.listEl.innerHTML = `<li class="error">${this.app.i18n.t('errorLoadParties')}</li>`;
        }
    }

    renderPartyList(parties) {
        this.listEl.innerHTML = '';
        if (parties.length === 0) {
            this.listEl.innerHTML = `<li>${this.app.i18n.t('noParties')}</li>`;
            return;
        }

        parties.forEach(party => {
            const li = document.createElement('li');
            li.dataset.partyId = party.id;
            li.innerHTML = `<span>${party.name}</span>`;
            li.addEventListener('click', () => this.selectParty(party.id));
            this.listEl.appendChild(li);
        });
    }

    showPanel(panelToShow) {
        this.inspectorPlaceholder.style.display = 'none';
        this.inspectorContent.style.display = 'block';
        [this.rosterView, this.editorView].forEach(p => {
            p.style.display = p === panelToShow ? 'block' : 'none';
        });
    }

    showEditorPanel() {
        if (!this.selectedPartyId) {
            status.setText('errorSelectPartyToAddChar', true);
            return;
        }
        this.showPanel(this.editorView);
    }

    async selectParty(partyId) {
        this.selectedPartyId = partyId;
        this.listEl.querySelectorAll('li').forEach(li => {
            li.classList.toggle('selected', li.dataset.partyId === String(partyId));
        });
        this.showPanel(this.rosterView);
        await this._loadAndRenderCharacters(partyId);
    }

    async _loadAndRenderCharacters(partyId) {
        this.characterListEl.innerHTML = '<li><div class="spinner"></div></li>';
        try {
            const characters = await apiCall(`/api/parties/${partyId}/characters`);
            this.characterListEl.innerHTML = '';
            if (characters.length === 0) {
                this.characterListEl.innerHTML = `<li>No characters in this party yet.</li>`;
                return;
            }
            characters.forEach(char => {
                const li = document.createElement('li');
                li.dataset.charId = char.id;
                li.innerHTML = `
                    <div>
                        <span class="char-info">${char.name}</span>
                        <span class="char-details">Lvl ${char.level} ${char.class}</span>
                    </div>
                    <button class="delete-icon-btn" data-char-id="${char.id}" data-char-name="${char.name}">
                        <span class="icon">&times;</span>
                        <span data-i18n-key="deleteBtn">${this.app.i18n.t('deleteBtn')}</span>
                    </button>
                `;
                this.characterListEl.appendChild(li);
            });
        } catch (error) {
            this.characterListEl.innerHTML = `<li class="error">Failed to load characters.</li>`;
        }
    }

    async addCharacter(useAI = false) {
        let charData;
        if (useAI) {
            const description = this.aiDescInput.value.trim();
            if (!description) return status.setText("errorCharDesc", true);

            const rules = this.app.settings?.Game?.default_ruleset;
            if (!rules) return status.setText("errorDefaultRules", true);

            this.aiGenerateBtn.disabled = true;
            status.setText('generatingChar', false, { rules: rules });
            try {
                const payload = {
                    description: description,
                    rules_kb: rules,
                    language: this.app.settings.Appearance.language || 'en'
                };
                charData = await apiCall('/api/game/generate-character', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                });
                status.setText('generatedChar', false, {name: charData.name, class: charData.class});
            } catch (error) {
                return; // apiCall helper shows status
            } finally {
                this.aiGenerateBtn.disabled = false;
                this.aiDescInput.value = '';
            }
        } else {
            const name = this.charNameInput.value.trim();
            const charClass = this.charClassInput.value.trim();
            const level = parseInt(this.charLevelInput.value, 10);
            if (!name || !charClass) return status.setText("errorCharNameClass", true);
            charData = { name, class: charClass, level, description: '', stats: {} };
        }

        const url = `/api/parties/${this.selectedPartyId}/characters`;
        await apiCall(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(charData),
        });
        this.charNameInput.value = '';
        this.charClassInput.value = '';
        this.charLevelInput.value = 1;
        await this.selectParty(this.selectedPartyId);
        // Reselect to show roster and refresh
    }

    async _handleCharacterDelete(event) {
        const deleteBtn = event.target.closest('.delete-icon-btn');
        if (!deleteBtn) return;
        event.stopPropagation();

        const characterId = deleteBtn.dataset.charId;
        const characterName = deleteBtn.dataset.charName;
        const confirmed = await confirmationModal.confirm(
            'deleteCharTitle', 'deleteCharMsg', { name: characterName }
        );
        if (confirmed) {
            await apiCall(`/api/characters/${characterId}`, { method: 'DELETE' });
            await this._loadAndRenderCharacters(this.selectedPartyId);
            status.setText('deleteCharSuccess', false, { name: characterName });
        }
    }
}
