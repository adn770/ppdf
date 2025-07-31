// dmme_lib/frontend/js/wizards/PartyWizard.js
import { apiCall } from './ApiHelper.js';

export class PartyWizard {
    constructor() {
        this.selectedPartyId = null;
    }

    init() {
        // This method now does nothing, as the open button is handled by main.js
    }

    _addEventListeners() {
        this.modal.querySelector('.close-btn').addEventListener('click', () => this.close());
        this.showCreateBtn.addEventListener('click', () => this.showCreatorPanel());
        this.createPartyBtn.addEventListener('click', () => this.createParty());
        this.addManualBtn.addEventListener('click', () => this.addCharacter(false));
        this.aiGenerateBtn.addEventListener('click', () => this.addCharacter(true));
    }

    async open() {
        this.modal = document.getElementById('party-wizard-modal');
        this.overlay = document.getElementById('modal-overlay');
        this.partyList = document.getElementById('party-list');
        this.characterList = document.getElementById('character-list');
        this.welcomePanel = document.getElementById('party-welcome-panel');
        this.creatorPanel = document.getElementById('party-creator-panel');
        this.characterEditorPanel = document.getElementById('character-editor-panel');
        this.showCreateBtn = document.getElementById('show-create-party-panel-btn');
        this.createPartyBtn = document.getElementById('create-party-btn');
        this.addManualBtn = document.getElementById('add-char-manual-btn');
        this.aiGenerateBtn = document.getElementById('ai-char-generate-btn');
        this.newPartyNameInput = document.getElementById('new-party-name-input');
        this.charNameInput = document.getElementById('char-name');
        this.charClassInput = document.getElementById('char-class');
        this.charLevelInput = document.getElementById('char-level');
        this.aiDescInput = document.getElementById('ai-char-desc');
        
        this._addEventListeners();
        this.overlay.style.display = 'block';
        this.modal.style.display = 'flex';
        this.showWelcomePanel();
        await this.loadParties();
    }

    close() {
        this.overlay.style.display = 'none';
        this.modal.style.display = 'none';
    }

    showPanel(panelToShow) {
        [
            this.welcomePanel, 
            this.creatorPanel, 
            this.characterEditorPanel
        ].forEach(p => {
            p.style.display = p === panelToShow ? 'block' : 'none';
        });
    }
    
    showWelcomePanel() {
        this.showPanel(this.welcomePanel);
        this.selectedPartyId = null;
        this.updatePartyListSelection();
        this.characterList.innerHTML = '';
    }

    showCreatorPanel() {
        this.showPanel(this.creatorPanel);
        this.newPartyNameInput.value = '';
        this.newPartyNameInput.focus();
        this.selectedPartyId = null;
        this.updatePartyListSelection();
        this.characterList.innerHTML = '';
    }
    
    async showCharacterEditorPanel(partyId) {
        this.showPanel(this.characterEditorPanel);
        this.selectedPartyId = partyId;
        this.updatePartyListSelection();
        await this.loadCharacters();
    }

    async loadParties() {
        this.partyList.innerHTML = '';
        const parties = await apiCall('/api/parties/');
        parties.forEach(party => {
            const li = document.createElement('li');
            li.dataset.partyId = party.id;
            li.dataset.partyName = party.name;
            const deleteBtnHTML = `<button class="delete-icon-btn" data-party-id="${party.id}">🗑️</button>`;
            li.innerHTML = `<span>${party.name}</span> ${deleteBtnHTML}`;
            
            li.querySelector('.delete-icon-btn').addEventListener('click', (e) => {
                e.stopPropagation();
                this.deleteParty(party.id, party.name);
            });
            li.addEventListener('click', () => this.showCharacterEditorPanel(party.id));
            
            this.partyList.appendChild(li);
        });
        this.updatePartyListSelection();
    }
    
    updatePartyListSelection() {
        this.partyList.querySelectorAll('li').forEach(li => {
            const isSelected = this.selectedPartyId !== null && 
                li.dataset.partyId === String(this.selectedPartyId);
            li.classList.toggle('selected', isSelected);
        });
    }

    async createParty() {
        const name = this.newPartyNameInput.value.trim();
        if (!name) {
            alert("Please enter a party name.");
            return;
        }
        const newParty = await apiCall('/api/parties/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name }),
        });
        await this.loadParties();
        this.showCharacterEditorPanel(newParty.id);
    }

    async deleteParty(partyId, partyName) {
        const msg = `Are you sure you want to delete the party "${partyName}"?`;
        if (confirm(msg)) {
            await apiCall(`/api/parties/${partyId}`, { method: 'DELETE' });
            if (String(this.selectedPartyId) === String(partyId)) {
                this.showWelcomePanel();
            }
            await this.loadParties();
        }
    }

    async loadCharacters() {
        if (!this.selectedPartyId) return;
        this.characterList.innerHTML = '';
        const url = `/api/parties/${this.selectedPartyId}/characters`;
        const characters = await apiCall(url);
        if (characters.length === 0) {
            const msg = 'No characters in this party yet.';
            this.characterList.innerHTML = `<li class="char-details" style="justify-content: center;">${msg}</li>`;
        } else {
            characters.forEach(char => {
                const li = document.createElement('li');
                li.innerHTML = `
                    <div>
                        <span class="char-info">${char.name}</span>
                        <span class="char-details">Lvl ${char.level} ${char.class}</span>
                    </div>
                    <button class="delete-icon-btn" data-char-id="${char.id}">🗑️</button>`;
                li.querySelector('.delete-icon-btn').addEventListener('click', 
                    () => this.deleteCharacter(char.id, char.name));
                this.characterList.appendChild(li);
            });
        }
    }

    async addCharacter(useAI = false) {
        let charData;
        if (useAI) {
            const description = this.aiDescInput.value.trim();
            if (!description) {
                alert("Please provide a character description.");
                return;
            }
            const rules = prompt("Which ruleset should the AI use? (e.g., D&D 5e)");
            if (!rules) return;

            this.aiGenerateBtn.disabled = true;
            this.aiGenerateBtn.textContent = '...';
            try {
                charData = await apiCall('/api/game/generate-character', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ description, rules_kb: rules }),
                });
            } finally {
                this.aiGenerateBtn.disabled = false;
                this.aiGenerateBtn.textContent = '✨';
                this.aiDescInput.value = '';
            }
        } else {
            const name = this.charNameInput.value.trim();
            const charClass = this.charClassInput.value.trim();
            const level = parseInt(this.charLevelInput.value, 10);
            if (!name || !charClass) {
                alert("Please provide a name and class.");
                return;
            }
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
        await this.loadCharacters();
    }

    async deleteCharacter(characterId, characterName) {
        if (confirm(`Are you sure you want to delete ${characterName}?`)) {
            await apiCall(`/api/characters/${characterId}`, { method: 'DELETE' });
            await this.loadCharacters();
        }
    }
}
