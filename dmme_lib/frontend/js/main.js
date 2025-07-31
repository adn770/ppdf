// dmme_lib/frontend/js/main.js
import { ImportWizard } from './wizards/ImportWizard.js';
import { PartyWizard } from './wizards/PartyWizard.js';
import { NewGameWizard } from './wizards/NewGameWizard.js';
import { GameplayHandler } from './GameplayHandler.js';

class App {
    constructor() {
        this.importWizard = new ImportWizard();
        this.partyWizard = new PartyWizard();
        this.gameplayHandler = new GameplayHandler();

        // Pass a callback to the NewGameWizard to start the game
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

                const isActive = accordionBody.classList.contains('active');
                accordionBody.classList.toggle('active');
                icon.textContent = isActive ? '+' : '-';

                // Optional: close other accordions
                document.querySelectorAll('.accordion-body').forEach(body => {
                    if (body !== accordionBody) {
                        body.classList.remove('active');
                        body.previousElementSibling.querySelector('.accordion-icon').textContent = '+';
                    }
                });
            });
        });
    }
}


document.addEventListener('DOMContentLoaded', () => {
    const app = new App();
    app.init();
});
