// dmme_lib/frontend/js/wizards/LoadCampaignWizard.js
import { apiCall } from './ApiHelper.js';
import { status } from '../ui.js';

export class LoadCampaignWizard {
    constructor(appInstance) {
        this.app = appInstance;
        this.selectedCampaign = null;
        this.campaigns = [];

        this.loadModal = document.getElementById('load-campaign-modal');
        this.recapModal = document.getElementById('session-recap-modal');
        this.overlay = document.getElementById('modal-overlay');
        // Load Modal Elements
        this.campaignListEl = document.getElementById('campaign-list');
        this.detailsContentEl = document.getElementById('campaign-details-content');
        this.loadConfirmBtn = document.getElementById('load-campaign-btn-confirm');
        // Recap Modal Elements
        this.recapHeaderEl = document.getElementById('recap-header');
        this.recapContentEl = document.getElementById('recap-content');
        this.recapContinueBtn = document.getElementById('recap-continue-btn');
        this._addEventListeners();
    }

    _addEventListeners() {
        this.loadModal.querySelector('.close-btn').addEventListener('click', () => this.close());
        this.recapModal.querySelector('.close-btn').addEventListener('click', () => this.close());
        this.loadConfirmBtn.addEventListener('click', () => this._handleLoadCampaign());
    }

    async open() {
        this.reset();
        this.overlay.style.display = 'block';
        this.loadModal.style.display = 'flex';
        this.app.i18n.translatePage();

        try {
            this.campaigns = await apiCall('/api/campaigns/');
            this._renderCampaignList();
        } catch (error) {
            this.detailsContentEl.innerHTML = `<p class="error">${this.app.i18n.t('errorLoadCampaigns')}</p>`;
        }
    }

    close() {
        this.overlay.style.display = 'none';
        this.loadModal.style.display = 'none';
        this.recapModal.style.display = 'none';
    }

    reset() {
        this.selectedCampaign = null;
        this.campaigns = [];
        this.campaignListEl.innerHTML = '';
        this.detailsContentEl.innerHTML = `<p>${this.app.i18n.t('selectCampaignPrompt')}</p>`;
        this.detailsContentEl.classList.add('placeholder');
        this.loadConfirmBtn.disabled = true;
    }

    _renderCampaignList() {
        if (this.campaigns.length === 0) {
            this.detailsContentEl.innerHTML = `<p>${this.app.i18n.t('noSavedCampaigns')}</p>`;
            return;
        }

        this.campaigns.forEach(campaign => {
            const li = document.createElement('li');
            li.dataset.campaignId = campaign.id;
            li.textContent = campaign.name;
            li.addEventListener('click', () => this._selectCampaign(campaign));
            this.campaignListEl.appendChild(li);
        });
    }

    _selectCampaign(campaign) {
        this.selectedCampaign = campaign;
        this.loadConfirmBtn.disabled = false;
        // Highlight selection
        this.campaignListEl.querySelectorAll('li').forEach(li => {
            li.classList.toggle('selected', li.dataset.campaignId == campaign.id);
        });
        // Show details
        this.detailsContentEl.classList.remove('placeholder');
        const formattedDate = new Date(campaign.updated_at).toLocaleString();
        this.detailsContentEl.innerHTML = `
            <h3>${campaign.name}</h3>
            <p><em>${this.app.i18n.t('lastPlayed')}: ${formattedDate}</em></p>
            <p>${campaign.description || this.app.i18n.t('noCampaignDesc')}</p>
        `;
    }

    async _handleLoadCampaign() {
        if (!this.selectedCampaign) return;
        try {
            const url = `/api/campaigns/${this.selectedCampaign.id}/latest-session`;
            const session = await apiCall(url);
            this._showRecap(session);
        } catch (error) {
            // If no previous session, just start a new one in that campaign.
            // This requires a "New Session" flow which is not yet designed.
            // For now, we will show an error.
            status.setText(error.message, true);
            console.error("Could not load latest session:", error);
        }
    }

    _showRecap(session) {
        this.loadModal.style.display = 'none';
        this.recapModal.style.display = 'flex';
        this.app.i18n.translatePage();

        const headerKey = 'recapHeader';
        this.recapHeaderEl.textContent = this.app.i18n.t(headerKey, {
            num: session.session_number
        });
        this.recapContentEl.textContent = session.journal_recap;

        this.recapContinueBtn.onclick = async () => {
            try {
                const state = await apiCall(`/api/campaigns/${this.selectedCampaign.id}/state`);
                if (state && state.game_config) {
                    const recoveredState = { narrativeHTML: state.narrative_log };
                    this.app.startGame(state.game_config, recoveredState);
                    this.close();
                } else {
                    throw new Error("Received invalid state from server.");
                }
            } catch (error) {
                // The apiCall helper will show a status bar error
                console.error("Failed to get campaign state:", error);
            }
        };
    }
}
