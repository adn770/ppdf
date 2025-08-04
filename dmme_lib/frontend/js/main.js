// dmme_lib/frontend/js/main.js
import { ImportWizard } from './wizards/ImportWizard.js';
import { PartyWizard } from './wizards/PartyWizard.js';
import { NewGameWizard } from './wizards/NewGameWizard.js';
import { LoadCampaignWizard } from './wizards/LoadCampaignWizard.js';
import { GameplayHandler } from './GameplayHandler.js';
import { SettingsManager } from './SettingsManager.js';
import { DiceRoller } from './components/DiceRoller.js';
import { DMInsight } from './components/DMInsight.js';
import { LibraryHub } from './hubs/LibraryHub.js';
import { PartyHub } from './hubs/PartyHub.js';
import { status } from './ui.js';
import { i18n } from './i18n.js';
import { apiCall } from './wizards/ApiHelper.js';
class App {
    constructor() {
        this.settingsManager = new SettingsManager(this);
        this.importWizard = new ImportWizard(this);
        this.partyWizard = new PartyWizard(this);
        this.newGameWizard = new NewGameWizard(this,
            (gameConfig) => this.startGame(gameConfig)
        );
        this.loadCampaignWizard = new LoadCampaignWizard(this);
        this.dmInsight = new DMInsight(this);
        this.gameplayHandler = new GameplayHandler(this, this.dmInsight);
        this.diceRoller = new DiceRoller(this.gameplayHandler);
        this.libraryHub = new LibraryHub(this);
        this.partyHub = new PartyHub(this);
        this.settings = null;
        this.i18n = i18n;
        this.currentView = 'game';
    }

    async init() {
        status.setText('initializing');
        this.settings = await this.settingsManager.loadSettings();
        this.settingsManager.applyTheme(this.settings.Appearance.theme);
        await this.i18n.init(this.settings.Appearance.language);
        this.populateQuickThemeSelector();

        document.querySelectorAll('.nav-btn').forEach(btn => {
            btn.addEventListener('click', () => this.switchView(btn.dataset.view));
        });
        this.updateHeader(this.currentView);
        await this.checkForRecovery();
    }

    switchView(viewName) {
        if (this.currentView === viewName) return;
        this.currentView = viewName;

        document.querySelectorAll('.view-container').forEach(v => v.classList.remove('active'));
        document.getElementById(`${viewName}-view`).classList.add('active');

        document.querySelectorAll('.nav-btn').forEach(b => {
            b.classList.toggle('active', b.dataset.view === viewName);
        });
        this.updateHeader(viewName);

        // Initialize hubs when they are first viewed
        if (viewName === 'library') {
            this.libraryHub.init();
        } else if (viewName === 'party') {
            this.partyHub.init();
        }
    }

    updateHeader(viewName) {
        const container = document.getElementById('contextual-header-controls');
        container.innerHTML = ''; // Clear existing buttons

        const createButton = (id, i18nKey, onClick) => {
            const button = document.createElement('button');
            button.id = id;
            button.dataset.i18nKey = i18nKey;
            button.textContent = this.i18n.t(i18nKey);
            button.addEventListener('click', onClick);
            return button;
        };

        if (viewName === 'game') {
            container.appendChild(createButton('new-game-btn', 'newGameBtn', () => this.newGameWizard.open()));
            container.appendChild(createButton('load-game-btn', 'loadGameBtn', () => this.loadCampaignWizard.open()));
        } else if (viewName === 'library') {
            const key = 'newKbBtn';
            container.appendChild(createButton('import-knowledge-btn', key, () => this.importWizard.open()));
        } else if (viewName === 'party') {
            container.appendChild(createButton('new-party-btn', 'newPartyBtn', () => this.partyWizard.open()));
        }

        // Settings button is common to all views but added here for consistency
        container.appendChild(createButton('settings-btn', 'settingsBtn', () => this.settingsManager.open()));
    }


    async checkForRecovery() {
        const recoveredState = await apiCall('/api/session/recover');
        const welcomeView = document.getElementById('welcome-view');
        const recoveryView = document.getElementById('recovery-view');
        const gameViewContent = document.getElementById('game-view-content');
        if (recoveredState && Object.keys(recoveredState).length > 0) {
            welcomeView.style.display = 'none';
            gameViewContent.style.display = 'none';
            this.i18n.translatePage();
            recoveryView.style.display = 'flex';

            document.getElementById('recover-continue-btn').onclick = () => {
                recoveryView.style.display = 'none';
                this.startGame(recoveredState.config, recoveredState);
            };
            document.getElementById('recover-discard-btn').onclick = async () => {
                await apiCall('/api/session/autosave', { method: 'DELETE' });
                recoveryView.style.display = 'none';
                welcomeView.style.display = 'block';
                status.setText('statusBarReady');
            };
        } else {
            welcomeView.style.display = 'block';
            gameViewContent.style.display = 'none';
            recoveryView.style.display = 'none';
            status.setText('statusBarReady');
        }
    }

    startGame(gameConfig, recoveredState = null) {
        console.log("Switching to game view with config:", gameConfig);
        this.gameplayHandler.endGame();

        this.switchView('game');
        document.getElementById('welcome-view').style.display = 'none';
        document.getElementById('recovery-view').style.display = 'none';
        const gameViewContent = document.getElementById('game-view-content');
        gameViewContent.style.display = 'flex';
        gameViewContent.classList.add('active');

        this.gameplayHandler.init(gameConfig, recoveredState);
    }

    populateQuickThemeSelector() {
        const mainSelector = document.getElementById('theme-selector');
        const quickSelector = document.getElementById('quick-theme-selector');
        if (mainSelector && quickSelector) {
            quickSelector.innerHTML = '';
            const placeholderOption = document.createElement('option');
            placeholderOption.value = "";
            placeholderOption.textContent = this.i18n.t('themeDefault');
            quickSelector.appendChild(placeholderOption);
            mainSelector.querySelectorAll('option').forEach(option => {
                if (option.value !== 'default') {
                    quickSelector.appendChild(option.cloneNode(true));
                }
            });
            quickSelector.value = "";
        }
    }
}


document.addEventListener('DOMContentLoaded', async () => {
    const app = new App();
    await app.init();
});
