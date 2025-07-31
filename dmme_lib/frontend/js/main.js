// dmme_lib/frontend/js/main.js
import { ImportWizard } from './wizards/ImportWizard.js';
import { PartyWizard } from './wizards/PartyWizard.js';
import { NewGameWizard } from './wizards/NewGameWizard.js';
import { GameplayHandler } from './GameplayHandler.js';
import { SettingsManager } from './SettingsManager.js';

class App {
    constructor() {
        this.importWizard = new ImportWizard();
        this.partyWizard = new PartyWizard();
        this.gameplayHandler = new GameplayHandler();
        this.settingsManager = new SettingsManager();

        this.newGameWizard = new NewGameWizard(
            (gameConfig) => this.startGame(gameConfig)
        );
    }

    init() {
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
    }

    startGame(gameConfig) {
        console.log("Switching to game view with config:", gameConfig);
        document.getElementById('welcome-view').style.display = 'none';
        const gameView = document.getElementById('game-view');
        gameView.style.display = 'flex';
        gameView.classList.add('active');

        this.gameplayHandler.init(gameConfig);
    }

    initAccordions() {
        document.querySelectorAll('.accordion-header').forEach(button => {
            button.addEventListener('click', () => {
                const accordionBody = button.nextElementSibling;
                const icon = button.querySelector('.accordion-icon');
                accordionBody.classList.toggle('active');
                icon.textContent = accordionBody.classList.contains('active') ? '-' : '+';
            });
        });
    }
}


document.addEventListener('DOMContentLoaded', async () => {
    // Apply theme on startup before initializing the app
    const settingsMgr = new SettingsManager();
    await settingsMgr.loadAndApplyTheme();

    const app = new App();
    app.init();
});
