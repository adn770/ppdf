// dmme_lib/frontend/js/hubs/PartyHub.js
import { apiCall } from '../wizards/ApiHelper.js';
import { status, confirmationModal } from '../ui.js';

const SAVE_CATEGORIES = ['poison', 'wands', 'paralysis', 'breath_weapon', 'spells'];

export class PartyHub {
    constructor(appInstance) {
        this.app = appInstance;
        this.isInitialized = false;
        this.selectedPartyId = null;
        this.selectedCharacterId = null;
        this.characterData = {}; // Cache for character data
        this.autosaveTimer = null;
        this._statSizerSpan = null; // For dynamic input sizing
        this.draggedItem = null;
    }

    _setupElements() {
        this.view = document.getElementById('party-view');
        if (!this.view) {
            console.error("Party Hub main view container not found!");
            return;
        }

        this.listEl = this.view.querySelector('#party-list-hub');
        this.inspectorPlaceholder = this.view.querySelector('#party-inspector-placeholder');
        this.creatorView = this.view.querySelector('#party-creator-hub');
        this.sheetView = this.view.querySelector('#character-sheet-hub');
        this.characterListEl = this.view.querySelector('#character-list-hub');
        this.showAddCharacterBtn =
            this.view.querySelector('#show-add-character-hub-btn');
        this.addPartyBtn = this.view.querySelector('#add-party-hub-btn');
        this.newPartyNameInput = this.view.querySelector('#new-party-name-hub-input');
        this.createPartyBtn = this.view.querySelector('#create-party-hub-btn');
        this.aiGenerateBtn = this.sheetView.querySelector('#ai-char-generate-hub-btn');
        this.rollStatsBtn = this.sheetView.querySelector('#roll-stats-btn');
        this.savesDisplay = this.sheetView.querySelector('#character-saves-display');
        this.tabs = this.sheetView.querySelectorAll('.hub-tab-btn');
        this.panes = this.sheetView.querySelectorAll('.hub-tab-pane');
        this.weaponsGrid = this.sheetView.querySelector('#weapons-grid');
        this.armourGrid = this.sheetView.querySelector('#armour-grid');
        this.ammunitionGrid = this.sheetView.querySelector('#ammunition-grid');
        this.inventoryGrid = this.sheetView.querySelector('#inventory-grid');
        this.spellSlotsGrid = this.sheetView.querySelector('#spell-slots-grid');
        this.spellListGrid = this.sheetView.querySelector('#spell-list-grid');
    }

    _createStatSizer() {
        this._statSizerSpan = document.createElement('span');
        const sizerStyles = {
            position: 'absolute',
            visibility: 'hidden',
            height: 'auto',
            width: 'auto',
            whiteSpace: 'pre',
            fontSize: '1.8em',
            fontWeight: 'bold',
            fontFamily: 'var(--font-family-sans)',
            padding: '4px 8px',
        };
        Object.assign(this._statSizerSpan.style, sizerStyles);
        document.body.appendChild(this._statSizerSpan);
    }

    _resizeStatInput(input) {
        if (!this._statSizerSpan) return;
        // Use placeholder for min-width, add a buffer
        this._statSizerSpan.textContent = input.value || '00';
        const newWidth = this._statSizerSpan.offsetWidth + 4;
        input.style.width = `${newWidth}px`;
    }

    init() {
        if (this.isInitialized) return;
        this._setupElements();
        this._createStatSizer();
        this.loadParties();
        this.addPartyBtn.addEventListener('click', () => this.showCreatorPanel());
        this.createPartyBtn.addEventListener('click', () => this.createParty());
        this.listEl.addEventListener('click', (e) => this._handlePartyDelete(e));
        this.showAddCharacterBtn.addEventListener(
            'click', () => this.showCreatorSheet()
        );
        this.characterListEl.addEventListener(
            'click', (e) => this._handleCharacterListClick(e)
        );
        this.aiGenerateBtn.addEventListener(
            'click', () => this.generateCharacterWithAI()
        );
        this.rollStatsBtn.addEventListener('click', () => this._rollRandomStats());
        this.tabs.forEach(tab => tab.addEventListener(
            'click', (e) => this._switchTab(e))
        );
        this.sheetView.querySelectorAll('[data-field]').forEach(input => {
            input.addEventListener('input', () => this._triggerAutosave());
        });
        this.sheetView.querySelectorAll('.score-input').forEach(input => {
            input.addEventListener('input', (e) => this._updateAllModifiers());
        });
        const equipmentPane = document.getElementById('character-pane-equipment');
        equipmentPane.addEventListener('click', (e) => {
            const addBtn = e.target.closest('.icon-btn');
            const deleteBtn = e.target.closest('.delete-row-btn');
            if (addBtn) {
                this._addEquipmentRow(addBtn.dataset.section);
            } else if (deleteBtn) {
                this._handleEquipmentDelete(deleteBtn);
            }
        });
        const inventoryPane = document.getElementById('character-pane-inventory');
        inventoryPane.addEventListener('click', (e) => {
            const addBtn = e.target.closest('.icon-btn');
            const deleteBtn = e.target.closest('.delete-row-btn');
            if (addBtn) {
                this._addEquipmentRow(addBtn.dataset.section);
            } else if (deleteBtn) {
                this._handleEquipmentDelete(deleteBtn);
            }
        });
        const spellsPane = document.getElementById('character-pane-spells');
        spellsPane.addEventListener('click', (e) => {
            const addBtn = e.target.closest('.icon-btn');
            const deleteBtn = e.target.closest('.delete-row-btn');
            if (addBtn) {
                this._addEquipmentRow(addBtn.dataset.section);
            } else if (deleteBtn) {
                this._handleEquipmentDelete(deleteBtn);
            }
        });
        const mainPane = document.getElementById('character-pane-main');
        mainPane.addEventListener('click', (e) => {
            const statBox = e.target.closest('.primary-stat-icon-box');
            if (statBox && !statBox.classList.contains('is-editing')) {
                this._switchToEditMode(statBox);
            }
        });
        // Add drag-drop listeners to equipment grids
        [
            this.weaponsGrid, this.armourGrid, this.ammunitionGrid, this.inventoryGrid,
            this.spellListGrid
        ].forEach(grid => {
            this._addDragDropListenersToGrid(grid);
        });
        this.isInitialized = true;
    }

    async loadParties() {
        this.listEl.innerHTML = `<li>${this.app.i18n.t('loadingParties')}</li>`;
        try {
            const parties = await apiCall('/api/parties/');
            this.renderPartyList(parties);
        } catch (error) {
            const key = 'errorLoadParties';
            this.listEl.innerHTML = `<li class="error">${this.app.i18n.t(key)}</li>`;
        }
    }

    renderPartyList(parties) {
        this.listEl.innerHTML = '';
        if (parties.length === 0) {
            this.listEl.innerHTML = `<li>${this.app.i18n.t('noParties')}</li>`;
            return;
        }

        parties.forEach(party => {
            const li = document.createElement('li');
            li.dataset.partyId = party.id;
            li.innerHTML = `
                <div class="item-main-content">
                    <span>${party.name}</span>
                </div>
                <button class="contextual-delete-btn slide-in-right"
                        data-party-id="${party.id}"
                        data-party-name="${party.name}">
                    <span class="icon">&times;</span>
                    <span data-i18n-key="deleteBtn">${this.app.i18n.t('deleteBtn')}</span>
                </button>
            `;
            const mainContent = li.querySelector('.item-main-content');
            mainContent.addEventListener('click', () => this.selectParty(party.id));
            this.listEl.appendChild(li);
        });
    }

    showPanel(panelToShow) {
        this.inspectorPlaceholder.style.display = 'none';
        [this.creatorView, this.sheetView].forEach(p => {
            p.style.display = p === panelToShow ? 'flex' : 'none';
        });
    }

    showCreatorPanel() {
        this.selectedPartyId = null;
        this.selectedCharacterId = null;
        this.listEl.querySelectorAll('li').forEach(
            li => li.classList.remove('selected')
        );
        this.characterListEl.innerHTML = '';
        this.newPartyNameInput.value = '';
        this.showPanel(this.creatorView);
        this.newPartyNameInput.focus();
    }

    showCreatorSheet() {
        if (!this.selectedPartyId) {
            status.setText('errorSelectPartyToAddChar', true);
            return;
        }
        this.selectedCharacterId = null; // New character mode
        this.clearSheet();
        this.showPanel(this.sheetView);
    }

    async selectParty(partyId) {
        this.selectedPartyId = partyId;
        this.listEl.querySelectorAll('li').forEach(li => {
            li.classList.toggle('selected', li.dataset.partyId === String(partyId));
        });
        await this._loadAndRenderCharacters(partyId);
    }

    async _loadAndRenderCharacters(partyId) {
        this.characterListEl.innerHTML = '<li><div class="spinner"></div></li>';
        try {
            const characters = await apiCall(`/api/parties/${partyId}/characters`);
            this.characterData[partyId] = characters; // Cache the data
            this.characterListEl.innerHTML = '';
            if (characters.length === 0) {
                this.characterListEl.innerHTML = `<li>No characters yet.</li>`;
                this.inspectorPlaceholder.style.display = 'flex';
                this.creatorView.style.display = 'none';
                this.sheetView.style.display = 'none';
                return;
            }
            characters.forEach(char => {
                const li = document.createElement('li');
                li.dataset.charId = char.id;
                li.innerHTML = `
                    <div class="item-main-content">
                        <span class="char-info">${char.name}</span>
                        <span class="char-details">Lvl ${char.level} ${char.class}</span>
                    </div>
                    <button class="contextual-delete-btn slide-in-right"
                            data-char-id="${char.id}"
                            data-char-name="${char.name}">
                        <span class="icon">&times;</span>
                        <span data-i18n-key="deleteBtn">
                            ${this.app.i18n.t('deleteBtn')}
                        </span>
                    </button>
                `;
                this.characterListEl.appendChild(li);
            });
            this.selectCharacter(characters[0].id);
        } catch (error) {
            const key = 'Failed to load characters.';
            this.characterListEl.innerHTML = `<li class="error">${key}</li>`;
        }
    }

    selectCharacter(characterId) {
        this.selectedCharacterId = characterId;
        this.characterListEl.querySelectorAll('li').forEach(li => {
            const id = String(characterId);
            li.classList.toggle('selected', li.dataset.charId === id);
        });
        this.displayCharacterSheet(characterId);
    }

    displayCharacterSheet(characterId) {
        const charData = this.characterData[this.selectedPartyId];
        const character = charData?.find(c => c.id === characterId);
        if (!character) return;
        this.sheetView.querySelectorAll('[data-field]').forEach(input => {
            const fieldPath = input.dataset.field;
            const getValue = (obj, path) =>
                path.split('.').reduce((o, k) => (o || {})[k], obj);
            const value = getValue(character, fieldPath);
            const displayValue = value !== undefined && value !== null ? value : '';

            if (input.classList.contains('primary-stat-input')) {
                input.value = displayValue;
                const displaySpan = input.previousElementSibling;
                if (displaySpan) displaySpan.textContent = displayValue;
            } else if (input.tagName === 'SPAN') {
                input.textContent = displayValue;
            } else {
                input.value = displayValue;
            }
        });
        this._updateAllModifiers();
        this._renderSaves(character.stats?.saves);
        this._renderWeapons(character.stats?.equipment?.weapons);
        this._renderArmour(character.stats?.equipment?.armour);
        this._renderAmmunition(character.stats?.equipment?.ammunition);
        this._renderInventory(character.stats?.inventory?.items);
        this._renderSpellSlots(character.stats?.spells?.slots);
        this._renderSpellList(character.stats?.spells?.list);
        this.showPanel(this.sheetView);
    }

    clearSheet() {
        this.sheetView.querySelectorAll('[data-field]').forEach(input => {
            if (input.classList.contains('primary-stat-input')) {
                input.value = '';
                const displaySpan = input.previousElementSibling;
                if (displaySpan) displaySpan.textContent = '';
            } else if (input.tagName === 'SPAN') {
                input.textContent = '';
            } else {
                input.value = '';
            }
        });
        const levelBox = this.view.querySelector('#level-box');
        levelBox.querySelector('.primary-stat-value').textContent = '1';
        levelBox.querySelector('.primary-stat-input').value = '1';

        this._updateAllModifiers();
        this._renderSaves(null);
        this._renderWeapons([]);
        this._renderArmour([]);
        this._renderAmmunition([]);
        this._renderInventory([]);
        this._renderSpellSlots(null);
        this._renderSpellList([]);
    }

    async createParty() {
        const name = this.newPartyNameInput.value.trim();
        if (!name) return status.setText('errorPartyName', true);
        await apiCall('/api/parties/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name }),
        });
        await this.loadParties();
        this.sheetView.style.display = 'none';
        this.creatorView.style.display = 'none';
        this.inspectorPlaceholder.style.display = 'flex';
    }

    _triggerAutosave() {
        clearTimeout(this.autosaveTimer);
        status.setText('savingStatus');
        this.autosaveTimer = setTimeout(() => this._performAutosave(), 1500);
    }

    _serializeGrid(gridElement, fields) {
        const items = [];
        const rows = gridElement.querySelectorAll(
            '.weapon-row, .armour-row, .ammunition-row, .inventory-row, .spell-list-row'
        );
        rows.forEach(row => {
            const item = {};
            fields.forEach(field => {
                const input = row.querySelector(`[data-field-key="${field}"]`);
                if (input) {
                    item[field] = input.value;
                }
            });
            if (Object.values(item).some(val => val && val.trim() !== '')) {
                items.push(item);
            }
        });
        return items;
    }

    async _performAutosave() {
        status.setText('savingStatus');
        const isNew = this.selectedCharacterId === null;
        let charData = {};
        this.sheetView.querySelectorAll('[data-field]').forEach(input => {
            const fieldPath = input.dataset.field;
            const value = (input.tagName === 'SPAN') ? input.textContent : input.value;
            const setValue = (obj, path, val) => {
                const keys = path.split('.');
                const lastKey = keys.pop();
                const lastObj = keys.reduce((o, k) => o[k] = o[k] || {}, obj);
                if (input.type === 'number' && val !== '') {
                    lastObj[lastKey] = Number(val);
                } else {
                    lastObj[lastKey] = val;
                }
            };
            setValue(charData, fieldPath, value);
        });
        if (!charData.stats) charData.stats = {};
        const wFields = ['name', 'type', 'to_hit', 'damage'];
        const aFields = ['name', 'type', 'bonus'];
        const amFields = ['description', 'count', 'to_hit', 'damage'];
        const iFields = ['description', 'quantity', 'weight', 'value'];
        const slFields = ['level', 'name', 'duration', 'range'];
        charData.stats.equipment = {
            weapons: this._serializeGrid(this.weaponsGrid, wFields),
            armour: this._serializeGrid(this.armourGrid, aFields),
            ammunition: this._serializeGrid(this.ammunitionGrid, amFields),
        };
        charData.stats.inventory = {
            items: this._serializeGrid(this.inventoryGrid, iFields)
        };
        if (!charData.stats.spells) charData.stats.spells = {};
        charData.stats.spells.list = this._serializeGrid(this.spellListGrid, slFields);

        const url = isNew
            ? `/api/parties/${this.selectedPartyId}/characters`
            : `/api/characters/${this.selectedCharacterId}`;
        const method = isNew ? 'POST' : 'PUT';
        try {
            const updatedChar = await apiCall(url, {
                method: method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(charData),
            });
            status.setText('savedStatus');
            if (isNew) {
                this.selectedCharacterId = updatedChar.id;
                await this._loadAndRenderCharacters(this.selectedPartyId);
                this.selectCharacter(updatedChar.id);
            }
            setTimeout(() => status.clear(), 2000);
        } catch (error) {
            status.setText('saveErrorStatus', true);
        }
    }

    async generateCharacterWithAI() {
        let description = document.getElementById('char-desc-hub').value.trim();
        if (!description) {
            const name = document.getElementById('char-name-hub').value.trim();
            const charClass = document.getElementById('char-class-hub').value.trim();
            const levelBox = this.view.querySelector('#level-box');
            const level = levelBox.querySelector('.primary-stat-value').textContent;
            if (!name || !charClass) return status.setText('errorCharNameClass', true);
            description = `${name}, a level ${level} ${charClass}`;
        }

        const rules = this.app.settings?.Game?.default_ruleset;
        if (!rules) return status.setText("errorDefaultRules", true);

        this.aiGenerateBtn.disabled = true;
        status.setText('generatingChar', false, { rules: rules });
        try {
            const payload = {
                description: description,
                rules_kb: rules,
                language: this.app.settings.Appearance.language || 'en'
            };
            const charData = await apiCall('/api/game/generate-character', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            this.displayCharacterSheet({ id: this.selectedCharacterId, ...charData });
            const genData = { name: charData.name, class: charData.class };
            status.setText('generatedChar', false, genData);
            await this._performAutosave();
        } catch (error) {
            // apiCall helper shows status
        } finally {
            this.aiGenerateBtn.disabled = false;
        }
    }

    _calculateModifier(score) {
        const scoreNum = parseInt(score, 10);
        if (isNaN(scoreNum)) return '';
        const modifier = Math.floor((scoreNum - 10) / 2);
        return modifier >= 0 ? `+${modifier}` : `${modifier}`;
    }

    _updateAllModifiers() {
        const scores = ['str', 'dex', 'con', 'int', 'wis', 'cha'];
        scores.forEach(score => {
            const scoreInput = this.sheetView.querySelector(`#char-${score}-hub`);
            const modDisplay = this.sheetView.querySelector(`#char-${score}-mod-hub`);
            if (scoreInput && modDisplay) {
                modDisplay.textContent = this._calculateModifier(scoreInput.value);
            }
        });
    }

    _renderSaves(saves) {
        this.savesDisplay.innerHTML = '';
        SAVE_CATEGORIES.forEach(key => {
            const value = saves?.[key] ?? 15;
            const name = key.replace(/_/g, ' ');

            const row = document.createElement('div');
            row.className = 'save-row';

            const label = document.createElement('label');
            label.textContent = name;

            const input = document.createElement('input');
            input.type = 'number';
            input.className = 'score-input cs-input-underline-small';
            input.dataset.field = `stats.saves.${key}`;

            input.value = value;

            input.addEventListener('input', () => this._triggerAutosave());

            row.appendChild(label);
            row.appendChild(input);
            this.savesDisplay.appendChild(row);
        });
    }

    _rollRandomStats() {
        const scores = ['str', 'dex', 'con', 'int', 'wis', 'cha'];
        const animationInterval = setInterval(() => {
            scores.forEach(score => {
                const scoreInput = this.sheetView.querySelector(`#char-${score}-hub`);
                if (scoreInput) {
                    scoreInput.value = Math.floor(Math.random() * 16) + 3;
                    this._updateAllModifiers();
                }
            });
        }, 50);
        setTimeout(() => {
            clearInterval(animationInterval);
            scores.forEach(score => {
                let total = 0;
                for (let i = 0; i < 3; i++) {
                    total += Math.floor(Math.random() * 6) + 1;
                }
                const scoreInput = this.sheetView.querySelector(`#char-${score}-hub`);
                if (scoreInput) scoreInput.value = total;
            });
            this._updateAllModifiers();
            this._triggerAutosave();
        }, 400);
    }

    _addEquipmentRow(section) {
        const classMap = {
            weapons: 'weapon-row', armour: 'armour-row', ammunition: 'ammunition-row',
            inventory: 'inventory-row', spells: 'spell-list-row'
        };
        const gridMap = {
            weapons: this.weaponsGrid,
            armour: this.armourGrid,
            ammunition: this.ammunitionGrid,
            inventory: this.inventoryGrid,
            spells: this.spellListGrid
        };
        const htmlMap = {
            weapons: `
                <div class="drag-handle">⠿</div>
                <input type="text" class="cs-input-underline-small"
                       data-field-key="name" placeholder="Description">
                <input type="text" class="cs-input-underline-small"
                        data-field-key="type" placeholder="Type">
                <input type="text" class="cs-input-underline-small"
                       data-field-key="to_hit" placeholder="To Hit">
                <input type="text" class="cs-input-underline-small"
                        data-field-key="damage" placeholder="Damage">
                <button class="delete-row-btn">🗑️</button>`,
            armour: `
                <div class="drag-handle">⠿</div>
                <input type="text" class="cs-input-underline-small"
                       data-field-key="name" placeholder="Description">
                <input type="text" class="cs-input-underline-small"
                       data-field-key="type" placeholder="Type">
                <input type="text" class="cs-input-underline-small"
                       data-field-key="bonus" placeholder="AC Bonus">
                <button class="delete-row-btn">🗑️</button>`,
            ammunition: `
                <div class="drag-handle">⠿</div>
                <input type="text" class="cs-input-underline-small"
                       data-field-key="description" placeholder="Description">
                <input type="number" class="cs-input-underline-small"
                       data-field-key="count" placeholder="Count">
                <input type="text" class="cs-input-underline-small"
                       data-field-key="to_hit" placeholder="To Hit">
                <input type="text" class="cs-input-underline-small"
                       data-field-key="damage" placeholder="Damage">
                <button class="delete-row-btn">🗑️</button>`,
            inventory: `
                <div class="drag-handle">⠿</div>
                <input type="text" class="cs-input-underline-small"
                       data-field-key="description" placeholder="Description">
                <input type="text" class="cs-input-underline-small"
                       data-field-key="quantity" placeholder="Qty">
                <input type="text" class="cs-input-underline-small"
                       data-field-key="weight" placeholder="Wt">
                <input type="text" class="cs-input-underline-small"
                       data-field-key="value" placeholder="Value">
                <button class="delete-row-btn">🗑️</button>`,
            spells: `
                <div class="drag-handle">⠿</div>
                <input type="text" class="cs-input-underline-small"
                       data-field-key="level" placeholder="Lvl">
                <input type="text" class="cs-input-underline-small"
                       data-field-key="name" placeholder="Spell Name">
                <input type="text" class="cs-input-underline-small"
                       data-field-key="duration" placeholder="Duration">
                <input type="text" class="cs-input-underline-small"
                       data-field-key="range" placeholder="Range">
                <button class="delete-row-btn">🗑️</button>`
        };
        const grid = gridMap[section];
        const newRow = document.createElement('div');
        newRow.className = classMap[section];
        newRow.draggable = true;
        newRow.innerHTML = htmlMap[section];
        newRow.querySelectorAll('input').forEach(input => {
            input.addEventListener('input', () => this._triggerAutosave());
        });
        grid.appendChild(newRow);
        this._triggerAutosave();
    }

    _handleEquipmentDelete(deleteButton) {
        const row = deleteButton.closest(
            '.weapon-row, .armour-row, .ammunition-row, .inventory-row, .spell-list-row'
        );
        row.remove();
        this._triggerAutosave();
    }

    _renderEquipment(grid, sectionName, items = [], createRowInnerHTML) {
        grid.innerHTML = '';
        const effectiveItems = (items && items.length > 0) ? items : [{}];
        effectiveItems.forEach(item => {
            const row = document.createElement('div');
            row.className = `${sectionName}-row`;
            row.draggable = true;
            row.innerHTML = createRowInnerHTML(item);
            row.querySelectorAll('input').forEach(input => {
                input.addEventListener('input', () => this._triggerAutosave());
            });
            grid.appendChild(row);
        });
    }

    _renderWeapons(weapons) {
        this._renderEquipment(this.weaponsGrid, 'weapon', weapons, (item = {}) => {
            return `
                <div class="drag-handle">⠿</div>
                <input type="text" class="cs-input-underline-small"
                       data-field-key="name" placeholder="Description"
                       value="${item.name || ''}">
                <input type="text" class="cs-input-underline-small"
                       data-field-key="type" placeholder="Type"
                       value="${item.type || ''}">
                <input type="text" class="cs-input-underline-small"
                       data-field-key="to_hit" placeholder="To Hit"
                       value="${item.to_hit || ''}">
                <input type="text" class="cs-input-underline-small"
                       data-field-key="damage" placeholder="Damage"
                       value="${item.damage || ''}">
                <button class="delete-row-btn">🗑️</button>
            `;
        });
    }

    _renderArmour(armour) {
        this._renderEquipment(this.armourGrid, 'armour', armour, (item = {}) => {
            return `
                <div class="drag-handle">⠿</div>
                <input type="text" class="cs-input-underline-small"
                       data-field-key="name" placeholder="Description"
                       value="${item.name || ''}">
                <input type="text" class="cs-input-underline-small"
                       data-field-key="type" placeholder="Type"
                       value="${item.type || ''}">
                <input type="text" class="cs-input-underline-small"
                       data-field-key="bonus" placeholder="AC Bonus"
                       value="${item.bonus || ''}">
                <button class="delete-row-btn">🗑️</button>
            `;
        });
    }

    _renderAmmunition(ammunition) {
        this._renderEquipment(
            this.ammunitionGrid, 'ammunition', ammunition, (item = {}) => {
                return `
                    <div class="drag-handle">⠿</div>
                    <input type="text" class="cs-input-underline-small"
                           data-field-key="description" placeholder="Description"
                           value="${item.description || ''}">
                    <input type="number" class="cs-input-underline-small"
                           data-field-key="count" placeholder="Count"
                           value="${item.count || ''}">
                    <input type="text" class="cs-input-underline-small"
                           data-field-key="to_hit" placeholder="To Hit"
                           value="${item.to_hit || ''}">
                    <input type="text" class="cs-input-underline-small"
                           data-field-key="damage" placeholder="Damage"
                           value="${item.damage || ''}">
                    <button class="delete-row-btn">🗑️</button>
                `;
            }
        );
    }

    _renderInventory(items) {
        this._renderEquipment(this.inventoryGrid, 'inventory', items, (item = {}) => {
            return `
                <div class="drag-handle">⠿</div>
                <input type="text" class="cs-input-underline-small"
                       data-field-key="description" placeholder="Description"
                       value="${item.description || ''}">
                <input type="text" class="cs-input-underline-small"
                       data-field-key="quantity" placeholder="Qty"
                       value="${item.quantity || ''}">
                <input type="text" class="cs-input-underline-small"
                       data-field-key="weight" placeholder="Wt"
                       value="${item.weight || ''}">
                <input type="text" class="cs-input-underline-small"
                       data-field-key="value" placeholder="Value"
                       value="${item.value || ''}">
                <button class="delete-row-btn">🗑️</button>
            `;
        });
    }

    _renderSpellList(spells) {
        this._renderEquipment(this.spellListGrid, 'spell-list', spells, (item = {}) => {
            return `
                <div class="drag-handle">⠿</div>
                <input type="text" class="cs-input-underline-small"
                       data-field-key="level" placeholder="Lvl"
                       value="${item.level || ''}">
                <input type="text" class="cs-input-underline-small"
                       data-field-key="name" placeholder="Spell Name"
                       value="${item.name || ''}">
                <input type="text" class="cs-input-underline-small"
                       data-field-key="duration" placeholder="Duration"
                       value="${item.duration || ''}">
                <input type="text" class="cs-input-underline-small"
                       data-field-key="range" placeholder="Range"
                       value="${item.range || ''}">
                <button class="delete-row-btn">🗑️</button>
            `;
        });
    }

    _renderSpellSlots(slots = {}) {
        this.spellSlotsGrid.innerHTML = '';
        for (let i = 1; i <= 6; i++) {
            const slot = slots[`lvl${i}`] || {};
            const group = document.createElement('div');
            group.className = 'form-group';
            group.innerHTML = `
                <label>Level ${i}</label>
                <div class="spell-slot-row">
                    <input type="number" class="cs-input-underline-small"
                           data-field="stats.spells.slots.lvl${i}.used"
                           placeholder="Used" value="${slot.used || ''}">
                    <span>/</span>
                    <input type="number" class="cs-input-underline-small"
                           data-field="stats.spells.slots.lvl${i}.max"
                           placeholder="Max" value="${slot.max || ''}">
                </div>
            `;
            const inputs = group.querySelectorAll('input');
            inputs.forEach(i => i.addEventListener(
                'input', () => this._triggerAutosave())
            );
            this.spellSlotsGrid.appendChild(group);
        }
    }

    _switchTab(event) {
        const targetPaneId = event.target.dataset.pane;
        this.tabs.forEach(tab =>
            tab.classList.toggle('active', tab.dataset.pane === targetPaneId)
        );
        this.panes.forEach(pane =>
            pane.classList.toggle('active', pane.id === targetPaneId)
        );
    }

    _switchToEditMode(statBox) {
        statBox.classList.add('is-editing');
        const display = statBox.querySelector('.primary-stat-value');
        const input = statBox.querySelector('.primary-stat-input');

        input.value = display.textContent;
        display.style.display = 'none';
        input.style.display = 'inline-block';
        this._resizeStatInput(input);
        input.focus();
        input.select();
        input.oninput = () => {
            input.value = input.value.replace(/[^0-9.+\-]/g, '');
            this._resizeStatInput(input);
        };

        const finishEditing = (saveChanges) => {
            this._switchToDisplayMode(statBox, saveChanges);
        };

        input.onblur = () => finishEditing(true);
        input.onkeydown = (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                finishEditing(true);
            } else if (e.key === 'Escape') {
                finishEditing(false);
            }
        };
    }

    _switchToDisplayMode(statBox, saveChanges) {
        statBox.classList.remove('is-editing');
        const display = statBox.querySelector('.primary-stat-value');
        const input = statBox.querySelector('.primary-stat-input');

        if (saveChanges) {
            display.textContent = input.value;
            this._triggerAutosave();
        }

        input.style.display = 'none';
        display.style.display = 'inline-block';

        input.onblur = null;
        input.onkeydown = null;
        input.oninput = null;
    }

    async _handlePartyDelete(event) {
        const deleteBtn = event.target.closest('.contextual-delete-btn');
        if (!deleteBtn) return;
        event.stopPropagation();

        const partyId = deleteBtn.dataset.partyId;
        const partyName = deleteBtn.dataset.partyName;
        const confirmed = await confirmationModal.confirm(
            'deletePartyTitle', 'deletePartyMsg', { name: partyName }
        );
        if (confirmed) {
            await apiCall(`/api/parties/${partyId}`, { method: 'DELETE' });
            if (String(this.selectedPartyId) === String(partyId)) {
                this.selectedPartyId = null;
                this.selectedCharacterId = null;
                this.characterListEl.innerHTML = '';
                this.sheetView.style.display = 'none';
                this.creatorView.style.display = 'none';
                this.inspectorPlaceholder.style.display = 'flex';
            }
            await this.loadParties();
            status.setText('deletePartySuccess', false, { name: partyName });
        }
    }

    async _handleCharacterListClick(event) {
        const li = event.target.closest('li');
        if (!li || !li.dataset.charId) return;

        const deleteBtn = event.target.closest('.contextual-delete-btn');
        if (deleteBtn) {
            event.stopPropagation();
            const characterId = deleteBtn.dataset.charId;
            const characterName = deleteBtn.dataset.charName;
            const confirmed = await confirmationModal.confirm(
                'deleteCharTitle', 'deleteCharMsg', { name: characterName }
            );
            if (confirmed) {
                await apiCall(`/api/characters/${characterId}`, { method: 'DELETE' });
                await this._loadAndRenderCharacters(this.selectedPartyId);
                const data = { name: characterName };
                status.setText('deleteCharSuccess', false, data);
            }
        } else {
            this.selectCharacter(parseInt(li.dataset.charId, 10));
        }
    }

    _addDragDropListenersToGrid(grid) {
        grid.addEventListener('dragstart', e => this._handleDragStart(e));
        grid.addEventListener('dragover', e => this._handleDragOver(e));
        grid.addEventListener('dragleave', e => this._handleDragLeave(e));
        grid.addEventListener('drop', e => this._handleDrop(e));
        grid.addEventListener('dragend', e => this._handleDragEnd(e));
    }

    _handleDragStart(e) {
        const target = e.target.closest('[draggable="true"]');
        if (target) {
            this.draggedItem = target;
            // A short delay allows the browser to render the drag image
            setTimeout(() => {
                target.classList.add('dragging');
            }, 0);
        }
    }

    _handleDragOver(e) {
        e.preventDefault();
        const grid = e.currentTarget;
        const afterElement = this._getDragAfterElement(grid, e.clientY);
        const currentPlaceholder = grid.querySelector('.drop-placeholder');
        if (afterElement == null) {
            if (!currentPlaceholder || currentPlaceholder.nextSibling) {
                if (currentPlaceholder) currentPlaceholder.remove();
                grid.appendChild(this._createPlaceholder());
            }
        } else {
            if (currentPlaceholder !== afterElement.previousSibling) {
                if (currentPlaceholder) currentPlaceholder.remove();
                grid.insertBefore(this._createPlaceholder(), afterElement);
            }
        }
    }

    _handleDragLeave(e) {
        const grid = e.currentTarget;
        if (!grid.contains(e.relatedTarget)) {
            const placeholder = grid.querySelector('.drop-placeholder');
            if (placeholder) placeholder.remove();
        }
    }

    _handleDrop(e) {
        e.preventDefault();
        const placeholder = e.currentTarget.querySelector('.drop-placeholder');
        if (placeholder) {
            e.currentTarget.insertBefore(this.draggedItem, placeholder);
            placeholder.remove();
            this._triggerAutosave();
        }
    }

    _handleDragEnd(e) {
        this.draggedItem.classList.remove('dragging');
        this.draggedItem = null;
        const placeholder = e.currentTarget.querySelector('.drop-placeholder');
        if (placeholder) {
            placeholder.remove();
        }
    }

    _getDragAfterElement(container, y) {
        const draggableElements =
            [...container.querySelectorAll('[draggable="true"]:not(.dragging)')];
        return draggableElements.reduce((closest, child) => {
            const box = child.getBoundingClientRect();
            const offset = y - box.top - box.height / 2;
            if (offset < 0 && offset > closest.offset) {
                return { offset: offset, element: child };
            } else {
                return closest;
            }
        }, { offset: Number.NEGATIVE_INFINITY }).element;
    }

    _createPlaceholder() {
        const placeholder = document.createElement('div');
        placeholder.className = 'drop-placeholder';
        if (this.draggedItem) {
            placeholder.style.height = `${this.draggedItem.offsetHeight}px`;
        }
        return placeholder;
    }
}
