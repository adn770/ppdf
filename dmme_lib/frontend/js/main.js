// dmme_lib/frontend/js/main.js
import { ImportWizard } from './wizards/ImportWizard.js';
import { NewGameWizard } from './wizards/NewGameWizard.js';
import { LoadCampaignWizard } from './wizards/LoadCampaignWizard.js';
import { GameplayHandler } from './GameplayHandler.js';
import { SettingsManager } from './SettingsManager.js';
import { DiceRoller } from './components/DiceRoller.js';
import { DMInsight } from './components/DMInsight.js';
import { LibraryHub } from './hubs/LibraryHub.js';
import { PartyHub } from './hubs/PartyHub.js';
import { Lightbox } from './components/Lightbox.js';
import { status, confirmationModal } from './ui.js';
import { i18n } from './i18n.js';
import { apiCall } from './wizards/ApiHelper.js';

class App {
    constructor() {
        this.settings = null;
        this.i18n = i18n;
        this.currentView = 'game';
    }

    async init() {
        status.setText('initializing');
        await this.loadComponents();
        mermaid.initialize({ startOnLoad: false, theme: 'dark' });

        // Initialize UI modules that depend on the now-loaded DOM
        confirmationModal.init();
        status.init();

        // Initialize managers and hubs after the DOM is populated
        this.settingsManager = new SettingsManager(this);
        this.importWizard = new ImportWizard(this);
        this.newGameWizard = new NewGameWizard(this,
            (gameConfig) => this.startGame(gameConfig)
        );
        this.loadCampaignWizard = new LoadCampaignWizard(this);
        this.dmInsight = new DMInsight(this);
        this.lightbox = new Lightbox();
        this.gameplayHandler = new GameplayHandler(this, this.dmInsight, this.lightbox);
        this.diceRoller = new DiceRoller(this.gameplayHandler);
        this.libraryHub = new LibraryHub(this, this.lightbox);
        this.partyHub = new PartyHub(this);

        this.settings = await this.settingsManager.loadSettings();
        this.settingsManager.applyTheme(this.settings.Appearance.theme);
        await this.i18n.init(this.settings.Appearance.language);
        this.populateQuickThemeSelector();

        document.querySelectorAll('.nav-btn').forEach(btn => {
            btn.addEventListener('click', () => this.switchView(btn.dataset.view));
        });

        // Add a cleanup listener to stop timers when the page is closed/reloaded
        window.addEventListener('beforeunload', () => this.cleanup());

        this.updateHeader(this.currentView);
        await this.checkForRecovery();
    }

    cleanup() {
        console.log("TRACE: Master cleanup running before page unload.");
        this.gameplayHandler.stopAutosave();
        this.partyHub.stopAutosave();
        this.settingsManager.stopAutosave();
    }

    async loadComponents() {
        const mainContent = document.getElementById('main-content');
        const body = document.body;

        const components = [
            { file: 'components/_game-view.html', target: mainContent },
            { file: 'components/_library-hub.html', target: mainContent },
            { file: 'components/_party-hub.html', target: mainContent },
            { file: 'components/_modals-wizards.html', target: body },
        ];
        await Promise.all(components.map(async (component) => {
            try {
                const response = await fetch(component.file);
                const html = await response.text();
                component.target.insertAdjacentHTML('beforeend', html);
            } catch (error) {
                console.error(`Failed to load component: ${component.file}`, error);
            }
        }));
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
            // This button is now handled inside the PartyHub itself.
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
                this.gameplayHandler.endGame(); // Clean up session and stop autosave
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
