// dmme_lib/frontend/js/hubs/PartyHub.js
import { apiCall } from '../wizards/ApiHelper.js';
import { status, confirmationModal } from '../ui.js';

export class PartyHub {
    constructor(appInstance) {
        this.app = appInstance;
        this.isInitialized = false;
        this.selectedPartyId = null;
        this.selectedCharacterId = null;
        this.characterData = {}; // Cache for character data

        // Defer all DOM selections to init() to ensure the DOM is ready
    }

    _setupElements() {
        // Get the main view container first
        this.view = document.getElementById('party-view');
        if (!this.view) {
            console.error("Party Hub main view container not found!");
            return;
        }

        // Scope all subsequent queries within the view container for robustness
        this.listEl = this.view.querySelector('#party-list-hub');
        this.inspectorPlaceholder = this.view.querySelector('#party-inspector-placeholder');
        this.creatorView = this.view.querySelector('#party-creator-hub');
        this.sheetView = this.view.querySelector('#character-sheet-hub');
        this.characterListEl = this.view.querySelector('#character-list-hub');
        this.showAddCharacterBtn = this.view.querySelector('#show-add-character-hub-btn');
        this.addPartyBtn = this.view.querySelector('#add-party-hub-btn');

        // Creator form inputs
        this.newPartyNameInput = this.view.querySelector('#new-party-name-hub-input');
        this.createPartyBtn = this.view.querySelector('#create-party-hub-btn');

        // Character Sheet Elements
        this.saveCharBtn = this.sheetView.querySelector('#save-character-btn');
        this.aiGenerateBtn = this.sheetView.querySelector('#ai-char-generate-hub-btn');
        this.rollStatsBtn = this.sheetView.querySelector('#roll-stats-btn');
        this.savesDisplay = this.sheetView.querySelector('#character-saves-display');
        this.sheetInputs = this.sheetView.querySelectorAll('[data-field]');
    }

    init() {
        if (this.isInitialized) return;
        this._setupElements();
        this.loadParties();
        this.addPartyBtn.addEventListener('click', () => this.showCreatorPanel());
        this.createPartyBtn.addEventListener('click', () => this.createParty());
        this.listEl.addEventListener('click', (e) => this._handlePartyDelete(e));
        this.showAddCharacterBtn.addEventListener('click', () => this.showCreatorSheet());
        this.characterListEl.addEventListener('click', (e) => this._handleCharacterListClick(e));
        this.saveCharBtn.addEventListener('click', () => this.saveCharacter());
        this.aiGenerateBtn.addEventListener('click', () => this.generateCharacterWithAI());
        this.rollStatsBtn.addEventListener('click', () => this._rollRandomStats());
        this.sheetInputs.forEach(input => {
            input.addEventListener('input', () => this.saveCharBtn.disabled = false);
        });
        this.sheetView.querySelectorAll('.score-input, .primary-stat-icon-box span').forEach(input => {
            input.addEventListener('input', (e) => this._updateAllModifiers());
        });
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
            li.innerHTML = `
                <div class="item-main-content">
                    <span>${party.name}</span>
                </div>
                <button class="contextual-delete-btn slide-in-right" data-party-id="${party.id}" data-party-name="${party.name}">
                    <span class="icon">&times;</span>
                    <span data-i18n-key="deleteBtn">${this.app.i18n.t('deleteBtn')}</span>
                </button>
            `;
            li.querySelector('.item-main-content').addEventListener('click', () => this.selectParty(party.id));
            this.listEl.appendChild(li);
        });
    }

    showPanel(panelToShow) {
        this.inspectorPlaceholder.style.display = 'none';
        [this.creatorView, this.sheetView].forEach(p => {
            p.style.display = p === panelToShow ? 'flex' : 'none';
        });
    }

    showCreatorPanel() {
        this.selectedPartyId = null;
        this.selectedCharacterId = null;
        this.listEl.querySelectorAll('li').forEach(li => li.classList.remove('selected'));
        this.characterListEl.innerHTML = '';
        this.newPartyNameInput.value = '';
        this.showPanel(this.creatorView);
        this.newPartyNameInput.focus();
    }

    showCreatorSheet() {
        if (!this.selectedPartyId) {
            status.setText('errorSelectPartyToAddChar', true);
            return;
        }
        this.selectedCharacterId = null; // New character mode
        this.clearSheet();
        this.showPanel(this.sheetView);
        this.saveCharBtn.disabled = false; // Enable save for new character
    }

    async selectParty(partyId) {
        this.selectedPartyId = partyId;
        this.listEl.querySelectorAll('li').forEach(li => {
            li.classList.toggle('selected', li.dataset.partyId === String(partyId));
        });
        await this._loadAndRenderCharacters(partyId);
    }

    async _loadAndRenderCharacters(partyId) {
        this.characterListEl.innerHTML = '<li><div class="spinner"></div></li>';
        try {
            const characters = await apiCall(`/api/parties/${partyId}/characters`);
            this.characterData[partyId] = characters; // Cache the data
            this.characterListEl.innerHTML = '';
            if (characters.length === 0) {
                this.characterListEl.innerHTML = `<li>No characters yet.</li>`;
                this.inspectorPlaceholder.style.display = 'flex';
                this.creatorView.style.display = 'none';
                this.sheetView.style.display = 'none';
                return;
            }
            characters.forEach(char => {
                const li = document.createElement('li');
                li.dataset.charId = char.id;
                li.innerHTML = `
                    <div class="item-main-content">
                        <span class="char-info">${char.name}</span>
                        <span class="char-details">Lvl ${char.level} ${char.class}</span>
                    </div>
                    <button class="contextual-delete-btn slide-in-right" data-char-id="${char.id}" data-char-name="${char.name}">
                        <span class="icon">&times;</span>
                        <span data-i18n-key="deleteBtn">${this.app.i18n.t('deleteBtn')}</span>
                    </button>
                `;
                this.characterListEl.appendChild(li);
            });
            // Auto-select the first character
            this.selectCharacter(characters[0].id);
        } catch (error) {
            this.characterListEl.innerHTML = `<li class="error">Failed to load characters.</li>`;
        }
    }
    
    selectCharacter(characterId) {
        this.selectedCharacterId = characterId;
        this.characterListEl.querySelectorAll('li').forEach(li => {
            li.classList.toggle('selected', li.dataset.charId === String(characterId));
        });
        this.displayCharacterSheet(characterId);
    }

    displayCharacterSheet(characterId) {
        const character = this.characterData[this.selectedPartyId]?.find(c => c.id === characterId);
        if (!character) return;

        this.sheetInputs.forEach(input => {
            const fieldPath = input.dataset.field;
            const getValue = (obj, path) => path.split('.').reduce((o, k) => (o || {})[k], obj);
            const value = getValue(character, fieldPath);
            const displayValue = value !== undefined && value !== null ? value : '';

            if (input.tagName === 'SPAN') {
                input.textContent = displayValue;
            } else {
                input.value = displayValue;
            }
        });
        this._updateAllModifiers();
        this._renderSaves(character.stats?.saves);
        this.saveCharBtn.disabled = true;
        this.showPanel(this.sheetView);
    }
    
    clearSheet() {
        this.sheetInputs.forEach(input => {
            if (input.tagName === 'SPAN') {
                input.textContent = '';
            } else {
                input.value = '';
            }
        });
        this.view.querySelector('#char-level-hub').textContent = '1';
        this._updateAllModifiers();
        this._renderSaves(null);
    }

    async createParty() {
        const name = this.newPartyNameInput.value.trim();
        if (!name) return status.setText('errorPartyName', true);
        await apiCall('/api/parties/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name }),
        });
        await this.loadParties();
        this.sheetView.style.display = 'none';
        this.creatorView.style.display = 'none';
        this.inspectorPlaceholder.style.display = 'flex';
    }

    async saveCharacter() {
        const isNew = this.selectedCharacterId === null;
        let charData = {};
        this.sheetInputs.forEach(input => {
            const fieldPath = input.dataset.field;
            const value = (input.tagName === 'SPAN') ? input.textContent : input.value;
            const setValue = (obj, path, val) => {
                const keys = path.split('.');
                const lastKey = keys.pop();
                const lastObj = keys.reduce((o, k) => o[k] = o[k] || {}, obj);
                lastObj[lastKey] = val;
            };
            setValue(charData, fieldPath, value);
        });
        const url = isNew ? `/api/parties/${this.selectedPartyId}/characters` : `/api/characters/${this.selectedCharacterId}`;
        const method = isNew ? 'POST' : 'PUT';
        const updatedChar = await apiCall(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(charData),
        });
        this.saveCharBtn.disabled = true;
        status.setText(isNew ? 'charCreated' : 'charUpdated', false, { name: charData.name });
        await this._loadAndRenderCharacters(this.selectedPartyId);
        if (isNew) {
            this.selectCharacter(updatedChar.id);
        }
    }
    
    async generateCharacterWithAI() {
        let description = document.getElementById('char-desc-hub').value.trim();
        if (!description) {
            const name = document.getElementById('char-name-hub').value.trim();
            const charClass = document.getElementById('char-class-hub').value.trim();
            const level = document.getElementById('char-level-hub').textContent;
            if (!name || !charClass) return status.setText('errorCharNameClass', true);
            description = `${name}, a level ${level} ${charClass}`;
        }

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
            const charData = await apiCall('/api/game/generate-character', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });

            this.displayCharacterSheet({ id: this.selectedCharacterId, ...charData });
            this.saveCharBtn.disabled = false;
            status.setText('generatedChar', false, { name: charData.name, class: charData.class });
        } catch (error) {
            // apiCall helper shows status
        } finally {
            this.aiGenerateBtn.disabled = false;
        }
    }

    _calculateModifier(score) {
        const scoreNum = parseInt(score, 10);
        if (isNaN(scoreNum)) return '';
        const modifier = Math.floor((scoreNum - 10) / 2);
        return modifier >= 0 ? `+${modifier}` : `${modifier}`;
    }

    _updateAllModifiers() {
        const scores = ['str', 'dex', 'con', 'int', 'wis', 'cha'];
        scores.forEach(score => {
            const scoreInput = this.sheetView.querySelector(`#char-${score}-hub`);
            const modDisplay = this.sheetView.querySelector(`#char-${score}-mod-hub`);
            if(scoreInput && modDisplay) {
                const value = scoreInput.tagName === 'SPAN' ? scoreInput.textContent : scoreInput.value;
                modDisplay.textContent = this._calculateModifier(value);
            }
        });
    }

    _renderSaves(saves) {
        this.savesDisplay.innerHTML = '';
        if (!saves || typeof saves !== 'object') return;
        for (const [key, value] of Object.entries(saves)) {
            const name = key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
            const saveEl = document.createElement('div');
            saveEl.className = 'save-item';
            saveEl.innerHTML = `<span>${name}</span><strong>${value}</strong>`;
            this.savesDisplay.appendChild(saveEl);
        }
    }

    _rollRandomStats() {
        const scores = ['str', 'dex', 'con', 'int', 'wis', 'cha'];
        scores.forEach(score => {
            let total = 0;
            for (let i = 0; i < 3; i++) {
                total += Math.floor(Math.random() * 6) + 1;
            }
            const scoreInput = this.sheetView.querySelector(`#char-${score}-hub`);
            if (scoreInput) {
                scoreInput.value = total;
            }
        });
        this._updateAllModifiers();
        this.saveCharBtn.disabled = false;
    }

    async _handlePartyDelete(event) {
        const deleteBtn = event.target.closest('.contextual-delete-btn');
        if (!deleteBtn) return;
        event.stopPropagation();

        const partyId = deleteBtn.dataset.partyId;
        const partyName = deleteBtn.dataset.partyName;
        const confirmed = await confirmationModal.confirm(
            'deletePartyTitle', 'deletePartyMsg', { name: partyName }
        );
        if (confirmed) {
            await apiCall(`/api/parties/${partyId}`, { method: 'DELETE' });
            if (String(this.selectedPartyId) === String(partyId)) {
                this.selectedPartyId = null;
                this.selectedCharacterId = null;
                this.characterListEl.innerHTML = '';
                this.sheetView.style.display = 'none';
                this.creatorView.style.display = 'none';
                this.inspectorPlaceholder.style.display = 'flex';
            }
            await this.loadParties();
            status.setText('deletePartySuccess', false, { name: partyName });
        }
    }

    async _handleCharacterListClick(event) {
        const li = event.target.closest('li');
        if (!li || !li.dataset.charId) return;

        const deleteBtn = event.target.closest('.contextual-delete-btn');
        if (deleteBtn) {
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
        } else {
            this.selectCharacter(parseInt(li.dataset.charId, 10));
        }
    }
}
