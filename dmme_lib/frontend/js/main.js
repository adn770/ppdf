// dmme_lib/frontend/js/main.js
import { ImportWizard } from './wizards/ImportWizard.js';
import { PartyWizard } from './wizards/PartyWizard.js';
import { NewGameWizard } from './wizards/NewGameWizard.js';
import { LoadCampaignWizard } from './wizards/LoadCampaignWizard.js';
import { GameplayHandler } from './GameplayHandler.js';
import { SettingsManager } from './SettingsManager.js';
import { DiceRoller } from './components/DiceRoller.js';
import { DMInsight } from './components/DMInsight.js';
import { status } from './ui.js';
import { i18n } from './i18n.js';
import { apiCall } from './wizards/ApiHelper.js';

class App {
    constructor() {
        // Pass a reference to the app instance for cross-component communication
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
        this.settings = null;
        this.i18n = i18n;
        // Make i18n service available to other components
    }

    async init() {
        status.setText('initializing');
        // Load settings first, as other components depend on them
        this.settings = await this.settingsManager.loadSettings();
        this.settingsManager.applyTheme(this.settings.Appearance.theme);

        // Initialize i18n before setting up event listeners
        await this.i18n.init(this.settings.Appearance.language);
        this.populateQuickThemeSelector();
        // Must be after i18n init
        document.getElementById('import-knowledge-btn').addEventListener('click',
            () => this.importWizard.open()
        );
        document.getElementById('party-manager-btn').addEventListener('click',
            () => this.partyWizard.open()
        );
        document.getElementById('new-game-btn').addEventListener('click',
            () => this.newGameWizard.open()
        );
        document.getElementById('load-game-btn').addEventListener('click',
            () => this.loadCampaignWizard.open()
        );
        document.getElementById('settings-btn').addEventListener('click',
            () => this.settingsManager.open()
        );
        this.initAccordions();

        // Check for a recoverable session before showing the welcome screen
        await this.checkForRecovery();
    }

    async checkForRecovery() {
        const recoveredState = await apiCall('/api/session/recover');
        const welcomeView = document.getElementById('welcome-view');
        const recoveryView = document.getElementById('recovery-view');

        // Check if the recovered state object is not empty
        if (recoveredState && Object.keys(recoveredState).length > 0) {
            welcomeView.style.display = 'none';
            // Translate the page content BEFORE showing the panel to prevent flicker
            this.i18n.translatePage();
            recoveryView.style.display = 'flex';

            document.getElementById('recover-continue-btn').onclick = () => {
                recoveryView.style.display = 'none';
                this.startGame(recoveredState.config, recoveredState);
            };
            document.getElementById('recover-discard-btn').onclick = async () => {
                // Clear the autosave file on the backend
                await apiCall('/api/session/autosave', { method: 'DELETE' });
                recoveryView.style.display = 'none';
                welcomeView.style.display = 'block';
                status.setText('statusBarReady');
            };
        } else {
            welcomeView.style.display = 'block';
            recoveryView.style.display = 'none';
            status.setText('statusBarReady');
        }
    }

    startGame(gameConfig, recoveredState = null) {
        console.log("Switching to game view with config:", gameConfig);
        // End any previous game session before starting a new one
        this.gameplayHandler.endGame();
        document.getElementById('welcome-view').style.display = 'none';
        const gameView = document.getElementById('game-view');
        gameView.style.display = 'flex';
        gameView.classList.add('active');

        this.gameplayHandler.init(gameConfig, recoveredState);
    }

    populateQuickThemeSelector() {
        const mainSelector = document.getElementById('theme-selector');
        const quickSelector = document.getElementById('quick-theme-selector');
        if (mainSelector && quickSelector) {
            // Clear the quick selector first
            quickSelector.innerHTML = '';
            // Add the placeholder option that reverts to the main setting
            const placeholderOption = document.createElement('option');
            placeholderOption.value = "";
            placeholderOption.textContent = this.i18n.t('themeDefault');
            quickSelector.appendChild(placeholderOption);

            // Copy all other themes from the main settings selector
            mainSelector.querySelectorAll('option').forEach(option => {
                // Exclude the original 'default' value to prevent duplication
                if (option.value !== 'default') {
                    quickSelector.appendChild(option.cloneNode(true));
                }
            });
            quickSelector.value = ""; // Start with the placeholder selected
        }
    }

    initAccordions() {
        document.querySelectorAll('.accordion-header').forEach(button => {
            button.addEventListener('click', () => {
                const accordionBody = button.nextElementSibling;
                const icon = button.querySelector('.accordion-icon');
                if (accordionBody.classList.contains('active')) {
                    accordionBody.classList.remove('active');
                    if (icon) icon.textContent = '+';
                } else {
                    accordionBody.classList.add('active');
                    if (icon) icon.textContent = '-';
                }
            });
        });
    }
}


document.addEventListener('DOMContentLoaded', async () => {
    const app = new App();
    await app.init();
});
