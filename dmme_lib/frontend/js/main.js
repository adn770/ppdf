// dmme_lib/frontend/js/main.js
import { ImportWizard } from './wizards/ImportWizard.js';
import { PartyWizard } from './wizards/PartyWizard.js';
import { NewGameWizard } from './wizards/NewGameWizard.js';

class App {
    constructor() {
        console.log("App constructor called.");
        this.importWizard = null;
        this.partyWizard = null;
        this.newGameWizard = null;
    }

    init() {
        console.log("App.init() called.");
        // Instantiating the wizards here, inside init(), guarantees the DOM is loaded.
        this.importWizard = new ImportWizard();
        this.partyWizard = new PartyWizard();
        this.newGameWizard = new NewGameWizard();

        console.log("All wizards instantiated. Setting up open triggers.");

        document.getElementById('import-knowledge-btn').addEventListener('click',
            () => this.importWizard.open()
        );
        document.getElementById('party-manager-btn').addEventListener('click',
            () => this.partyWizard.open()
        );
        document.getElementById('new-game-btn').addEventListener('click',
            () => this.newGameWizard.open()
        );
    }
}


console.log("main.js script loaded.");
document.addEventListener('DOMContentLoaded', () => {
    console.log("DOMContentLoaded event fired.");
    const app = new App();
    app.init();
});
