// dmme_lib/frontend/js/wizards/NewGameWizard.js
import { apiCall } from './ApiHelper.js';
import { status } from '../ui.js';

export class NewGameWizard {
    constructor(appInstance, onStartGameCallback) {
        this.app = appInstance;
        this.onStartGame = onStartGameCallback;
        this.modal = document.getElementById('new-game-wizard-modal');
        this.overlay = document.getElementById('modal-overlay');
        this.rulesSelect = document.getElementById('game-rules-kb');
        this.moduleSelect = document.getElementById('game-module-kb');
        this.settingSelect = document.getElementById('game-setting-kb');
        this.partySelect = document.getElementById('game-party-selector');
        this.moduleGroup = document.getElementById('game-module-group');
        this.settingGroup = document.getElementById('game-setting-group');
        this.gameModeRadios = document.querySelectorAll('input[name="game-mode"]');
        this.startGameBtn = document.getElementById('start-game-btn');
        
        this._addEventListeners();
    }

    _addEventListeners() {
        this.modal.querySelector('.close-btn').addEventListener('click', () => this.close());
        this.gameModeRadios.forEach(radio => {
            radio.addEventListener('change', () => this.handleModeChange());
        });
        this.startGameBtn.addEventListener('click', () => this.startGame());
    }

    async open() {
        this.overlay.style.display = 'block';
        this.modal.style.display = 'flex';
        await this.populateSelectors();
        this.handleModeChange();
    }

    close() {
        this.overlay.style.display = 'none';
        this.modal.style.display = 'none';
    }

    async populateSelectors() {
        const kbs = await apiCall('/api/knowledge/');
        const parties = await apiCall('/api/parties/');

        // Clear existing options
        [this.rulesSelect, this.moduleSelect, this.settingSelect, this.partySelect].forEach(
            sel => sel.innerHTML = ''
        );

        // Populate KBs filtered by type, accessing the nested metadata property
        kbs.forEach(kb => {
            const option = new Option(`${kb.name} (${kb.count} docs)`, kb.name);
            if (kb.metadata?.kb_type === 'rules') this.rulesSelect.add(option.cloneNode(true));
            if (kb.metadata?.kb_type === 'module') this.moduleSelect.add(option.cloneNode(true));
            if (kb.metadata?.kb_type === 'setting') this.settingSelect.add(option.cloneNode(true));
        });

        // Set the default preferred ruleset from settings
        const defaultRuleset = this.app.settings?.Game?.default_ruleset;
        if (defaultRuleset) {
            this.rulesSelect.value = defaultRuleset;
        }

        if (parties.length === 0) {
            this.partySelect.innerHTML = '<option value="">No parties created yet</option>';
            this.startGameBtn.disabled = true;
        } else {
             parties.forEach(party => {
                const option = new Option(party.name, party.id);
                this.partySelect.add(option);
            });
            this.startGameBtn.disabled = false;
        }
    }

    handleModeChange() {
        const selectedMode = document.querySelector('input[name="game-mode"]:checked').value;
        if (selectedMode === 'module') {
            this.moduleGroup.style.display = 'block';
            this.settingGroup.style.display = 'none';
        } else {
            this.moduleGroup.style.display = 'none';
            this.settingGroup.style.display = 'block';
        }
    }

    startGame() {
        const selectedMode = document.querySelector('input[name="game-mode"]:checked').value;
        const gameConfig = {
            mode: selectedMode,
            rules: this.rulesSelect.value,
            party: this.partySelect.value,
            module: selectedMode === 'module' ? this.moduleSelect.value : null,
            setting: selectedMode === 'freestyle' ? this.settingSelect.value : null
        };
        if (!gameConfig.rules || !gameConfig.party) {
            status.setText("A Rules System and a Party are required to start a game.", true);
            return;
        }

        console.log("Starting game with config:", gameConfig);
        this.onStartGame(gameConfig);
        this.close();
    }
}
