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
        this.modelOverrideSelect = document.getElementById('game-llm-model-override');
        this.languageOverrideSelect = document.getElementById('game-language-override');
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
        const [kbs, parties, models] = await Promise.all([
            apiCall('/api/knowledge/'),
            apiCall('/api/parties/'),
            apiCall('/api/ollama/models'),
        ]);

        // Clear existing options
        [
            this.rulesSelect, this.moduleSelect, this.settingSelect,
            this.partySelect, this.modelOverrideSelect, this.languageOverrideSelect
        ].forEach(sel => sel.innerHTML = '');

        // Populate KBs filtered by type
        kbs.forEach(kb => {
            const option = new Option(`${kb.name} (${kb.count} docs)`, kb.name);
            if (kb.metadata?.kb_type === 'rules') this.rulesSelect.add(option.cloneNode(true));
            if (kb.metadata?.kb_type === 'module') this.moduleSelect.add(option.cloneNode(true));
            if (kb.metadata?.kb_type === 'setting') this.settingSelect.add(option.cloneNode(true));
        });

        // Populate Model Override
        const defaultModelOpt = new Option("Use Settings Default", "");
        this.modelOverrideSelect.add(defaultModelOpt);
        models.forEach(model => {
            if (model.type_hint === 'text') {
                this.modelOverrideSelect.add(new Option(model.name, model.name));
            }
        });

        // Populate Language Override
        const defaultLangOpt = new Option("Use Settings Default", "");
        const langOptions = [
            { value: "en", key: "formLangEn" },
            { value: "es", key: "formLangEs" },
            { value: "ca", key: "formLangCa" },
        ];
        this.languageOverrideSelect.add(defaultLangOpt);
        langOptions.forEach(lang => {
            this.languageOverrideSelect.add(new Option(this.app.i18n.t(lang.key), lang.value));
        });

        // Set defaults from settings
        const defaultRuleset = this.app.settings?.Game?.default_ruleset;
        if (defaultRuleset) this.rulesSelect.value = defaultRuleset;

        const defaultSetting = this.app.settings?.Game?.default_setting;
        if (defaultSetting) this.settingSelect.value = defaultSetting;

        if (parties.length === 0) {
            const key = 'noParties';
            this.partySelect.innerHTML = `<option value="">${this.app.i18n.t(key)}</option>`;
            this.startGameBtn.disabled = true;
        } else {
             parties.forEach(party => {
                this.partySelect.add(new Option(party.name, party.id));
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
            setting: selectedMode === 'freestyle' ? this.settingSelect.value : null,
            // Add overrides only if a specific value is chosen
            llm_model: this.modelOverrideSelect.value || undefined,
            language: this.languageOverrideSelect.value || undefined,
        };

        // Clean up undefined keys before passing the config
        Object.keys(gameConfig).forEach(key => gameConfig[key] === undefined && delete gameConfig[key]);

        if (!gameConfig.rules || !gameConfig.party) {
            status.setText("errorStartGame", true);
            return;
        }

        console.log("Starting game with config:", gameConfig);
        this.onStartGame(gameConfig);
        this.close();
    }
}
