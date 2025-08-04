// dmme_lib/frontend/js/hubs/PartyHub.js
import { apiCall } from '../wizards/ApiHelper.js';
export class PartyHub {
    constructor(appInstance) {
        this.app = appInstance;
        this.isInitialized = false;
        this.selectedPartyId = null;

        this.view = document.getElementById('party-view');
        this.listEl = document.getElementById('party-list-hub');
        this.inspectorPlaceholder = document.getElementById('party-inspector-placeholder');
        this.inspectorContent = document.getElementById('party-inspector-content');
        this.rosterView = document.getElementById('party-roster-hub');
        this.editorView = document.getElementById('character-editor-hub');
        this.characterListEl = document.getElementById('character-list-hub');
        this.showAddCharacterBtn = document.getElementById('show-add-character-hub-btn');
    }

    init() {
        if (this.isInitialized) return;
        this.loadParties();
        this.showAddCharacterBtn.addEventListener('click', () => this.showEditorPanel());
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
            // This could be enhanced to prompt party creation if none is selected
            console.warn("Cannot add a character without a selected party.");
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
                    <button class="delete-icon-btn" data-char-id="${char.id}" data-char-name="${char.name}">🗑️</button>
                `;
                this.characterListEl.appendChild(li);
            });
        } catch (error) {
            this.characterListEl.innerHTML = `<li class="error">Failed to load characters.</li>`;
        }
    }
}
