// dmme_lib/frontend/js/hubs/PartyHub.js
import { apiCall } from '../wizards/ApiHelper.js';

export class PartyHub {
    constructor(appInstance) {
        this.app = appInstance;
        this.isInitialized = false;
        this.selectedParty = null;

        this.view = document.getElementById('party-view');
        this.listEl = document.getElementById('party-list-hub');
        this.inspectorPlaceholder = document.getElementById('party-inspector-placeholder');
    }

    init() {
        if (this.isInitialized) return;
        this.loadParties();
        this.isInitialized = true;
    }

    async loadParties() {
        this.listEl.innerHTML = `<li>${this.app.i18n.t('loadingParties')}</li>`; // Placeholder
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
            // Add click listener for future inspector functionality
            // li.addEventListener('click', () => this.showPartyDetails(party));
            this.listEl.appendChild(li);
        });
    }
}
