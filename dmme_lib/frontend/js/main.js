// dmme_lib/frontend/js/main.js
import { ImportWizard } from './wizards/ImportWizard.js';
import { PartyWizard } from './wizards/PartyWizard.js';
import { NewGameWizard } from './wizards/NewGameWizard.js';
import { GameplayHandler } from './GameplayHandler.js';
import { SettingsManager } from './SettingsManager.js';
import { DiceRoller } from './components/DiceRoller.js';
import { status } from './ui.js';
import { i18n } from './i18n.js';

class App {
    constructor() {
        // Pass a reference to the app instance for cross-component communication
        this.settingsManager = new SettingsManager(this);
        this.importWizard = new ImportWizard(this);
        this.partyWizard = new PartyWizard(this);
        this.gameplayHandler = new GameplayHandler(this);
        this.newGameWizard = new NewGameWizard(this,
            (gameConfig) => this.startGame(gameConfig)
        );
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
        this.populateQuickThemeSelector(); // Must be after i18n init
        document.getElementById('import-knowledge-btn').addEventListener('click',
            () => this.importWizard.open()
        );
        document.getElementById('party-manager-btn').addEventListener('click',
            () => this.partyWizard.open()
        );
        document.getElementById('new-game-btn').addEventListener('click',
            () => this.newGameWizard.open()
        );
        document.getElementById('settings-btn').addEventListener('click',
            () => this.settingsManager.open()
        );
        this.initAccordions();
        status.setText('statusBarReady');
    }

    startGame(gameConfig) {
        console.log("Switching to game view with config:", gameConfig);
        document.getElementById('welcome-view').style.display = 'none';
        const gameView = document.getElementById('game-view');
        gameView.style.display = 'flex';
        gameView.classList.add('active');

        this.gameplayHandler.init(gameConfig);
    }

    populateQuickThemeSelector() {
        const mainSelector = document.getElementById('theme-selector');
        const quickSelector = document.getElementById('quick-theme-selector');
        if (mainSelector && quickSelector) {
            quickSelector.innerHTML = mainSelector.innerHTML;
            const defaultOption = document.createElement('option');
            defaultOption.value = "";
            defaultOption.textContent = this.i18n.t('themeDefault');
            quickSelector.prepend(defaultOption);
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
