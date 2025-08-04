// dmme_lib/frontend/js/wizards/PartyWizard.js
import { apiCall } from './ApiHelper.js';
import { status, confirmationModal } from '../ui.js';

export class PartyWizard {
    constructor(appInstance) {
        this.app = appInstance;
        this.selectedPartyId = null;
        this.modal = document.getElementById('party-wizard-modal');
        this.overlay = document.getElementById('modal-overlay');
        this.partyList = document.getElementById('party-list');
        this.welcomePanel = document.getElementById('party-welcome-panel');
        this.creatorPanel = document.getElementById('party-creator-panel');
        this.showCreateBtn = document.getElementById('show-create-party-panel-btn');
        this.createPartyBtn = document.getElementById('create-party-btn');
        this.newPartyNameInput = document.getElementById('new-party-name-input');
        
        this._addEventListeners();
    }

    _addEventListeners() {
        this.modal.querySelector('.close-btn').addEventListener('click', () => this.close());
        this.showCreateBtn.addEventListener('click', () => this.showCreatorPanel());
        this.createPartyBtn.addEventListener('click', () => this.createParty());
    }

    async open() {
        this.overlay.style.display = 'block';
        this.modal.style.display = 'flex';
        this.showWelcomePanel();
        await this.loadParties();
    }

    close() {
        this.overlay.style.display = 'none';
        this.modal.style.display = 'none';
        // Refresh the hub list in case changes were made
        if (this.app.partyHub.isInitialized) {
            this.app.partyHub.loadParties();
        }
    }

    showPanel(panelToShow) {
        // This modal now only has two relevant panels
        [this.welcomePanel, this.creatorPanel].forEach(p => {
            p.style.display = p === panelToShow ? 'block' : 'none';
        });
        document.getElementById('character-editor-panel').style.display = 'none';
    }
    
    showWelcomePanel() {
        this.showPanel(this.welcomePanel);
        this.selectedPartyId = null;
        this.updatePartyListSelection();
    }

    showCreatorPanel() {
        this.showPanel(this.creatorPanel);
        this.newPartyNameInput.value = '';
        this.newPartyNameInput.focus();
        this.selectedPartyId = null;
        this.updatePartyListSelection();
    }

    async loadParties() {
        this.partyList.innerHTML = '';
        const parties = await apiCall('/api/parties/');
        parties.forEach(party => {
            const li = document.createElement('li');
            li.dataset.partyId = party.id;
            li.dataset.partyName = party.name;
            const btnHTML =
                `<button class="delete-icon-btn" data-party-id="${party.id}">🗑️</button>`;
            li.innerHTML = `<span>${party.name}</span> ${btnHTML}`;
            
            li.querySelector('.delete-icon-btn').addEventListener('click', (e) => {
                e.stopPropagation();
                this.deleteParty(party.id, party.name);
            });
            // Clicking a party now does nothing in this simplified modal
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
            status.setText("errorPartyName", true);
            return;
        }
        await apiCall('/api/parties/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name }),
        });
        await this.loadParties();
        this.showWelcomePanel();
    }

    async deleteParty(partyId, partyName) {
        const confirmed = await confirmationModal.confirm(
            'deletePartyTitle',
            'deletePartyMsg',
            { name: partyName }
        );
        if (confirmed) {
            await apiCall(`/api/parties/${partyId}`, { method: 'DELETE' });
            if (String(this.selectedPartyId) === String(partyId)) {
                this.showWelcomePanel();
            }
            await this.loadParties();
            status.setText('deletePartySuccess', false, { name: partyName });
        }
    }
}
