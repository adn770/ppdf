// dmme_lib/frontend/js/GameplayHandler.js
import { showGameSpinner, hideGameSpinner } from './ui.js';

export class GameplayHandler {
    constructor(appInstance) {
        this.app = appInstance;
        this.gameConfig = null;
        this.narrativeView = document.getElementById('narrative-view');
        this.playerInput = document.getElementById('player-input');
        this.sendCommandBtn = document.getElementById('send-command-btn');
        this.kbDisplay = document.getElementById('kb-display');
        this.dmInsight = '';

        // New style controls
        this.quickThemeSelector = document.getElementById('quick-theme-selector');
        this.fontSizeSlider = document.getElementById('font-size-slider');
        this.lineHeightSlider = document.getElementById('line-height-slider');

        this._addEventListeners();
    }

    init(gameConfig) {
        this.gameConfig = gameConfig;
        console.log("GameplayHandler initialized with config:", this.gameConfig);

        this._updateKnowledgePanel();
        this._applyInitialStyles();
        this._startNarration();
    }

    _addEventListeners() {
        this.sendCommandBtn.addEventListener('click', () => this._sendCommandFromInput());
        this.playerInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this._sendCommandFromInput();
            }
        });
        this.quickThemeSelector.addEventListener('change', (e) => this._applyQuickTheme(e));
        this.fontSizeSlider.addEventListener('input', (e) => this._updateNarrativeStyle(e));
        this.lineHeightSlider.addEventListener('input', (e) => this._updateNarrativeStyle(e));
    }

    _applyInitialStyles() {
        this.narrativeView.style.fontSize = `${this.fontSizeSlider.value}rem`;
        this.narrativeView.style.lineHeight = this.lineHeightSlider.value;
        // Reset quick theme selector to its placeholder
        this.quickThemeSelector.value = "";
    }

    _applyQuickTheme(event) {
        const themeName = event.target.value;
        // Use the default theme if the placeholder is selected
        const themeToApply = themeName || this.app.settings.Appearance.theme;
        this.app.settingsManager.applyTheme(themeToApply);
    }

    _updateNarrativeStyle(event) {
        const value = event.target.value;
        const type = event.target.id;
        if (type === 'font-size-slider') {
            this.narrativeView.style.fontSize = `${value}rem`;
        } else if (type === 'line-height-slider') {
            this.narrativeView.style.lineHeight = value;
        }
    }

    _updateKnowledgePanel() {
        const i18n = this.app.i18n;
        let kbHtml = `<span>${i18n.t('kbDisplayRules')}: <strong>${this.gameConfig.rules}</strong></span>`;
        if (this.gameConfig.mode === 'module') {
            kbHtml += ` | <span>${i18n.t('kbDisplayModule')}: <strong>${this.gameConfig.module}</strong></span>`;
        } else {
            kbHtml += ` | <span>${i18n.t('kbDisplaySetting')}: <strong>${this.gameConfig.setting}</strong></span>`;
        }
        this.kbDisplay.innerHTML = kbHtml;
    }

    async _startNarration() {
        this.playerInput.disabled = true;
        this.sendCommandBtn.disabled = true;
        this.narrativeView.innerHTML = ''; // Clear view for new game
        showGameSpinner();
        const { entry, paragraph } = this._createAiResponseEntry();
        try {
            const response = await fetch('/api/game/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ config: this.gameConfig }),
            });
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            await this._processStream(response, entry, paragraph);
        } catch (error) {
            console.error("Failed to get response from game start API:", error);
            paragraph.textContent = "Error: Could not start the game narration.";
        } finally {
            this.playerInput.disabled = false;
            this.sendCommandBtn.disabled = false;
            this.playerInput.focus();
            hideGameSpinner();
        }
    }

    submitCommand(commandText) {
        this._processAndSendCommand(commandText);
    }

    _sendCommandFromInput() {
        const commandText = this.playerInput.value.trim();
        if (!commandText) return;
        this.playerInput.value = '';
        this._processAndSendCommand(commandText);
    }

    async _processAndSendCommand(commandText) {
        if (!commandText) return;
        this._renderPlayerCommand(commandText);
        this.playerInput.disabled = true;
        this.sendCommandBtn.disabled = true;
        showGameSpinner();

        const { entry, paragraph } = this._createAiResponseEntry();
        try {
            const response = await fetch('/api/game/command', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ command: commandText, config: this.gameConfig }),
            });
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            await this._processStream(response, entry, paragraph);
        } catch (error) {
            console.error("Failed to get response from game command API:", error);
            paragraph.textContent = "Error: Could not connect to the game server.";
        } finally {
            this.playerInput.disabled = false;
            this.sendCommandBtn.disabled = false;
            this.playerInput.focus();
            hideGameSpinner();
        }
    }

    _renderPlayerCommand(text) {
        const entry = document.createElement('div');
        entry.className = 'narrative-entry player-command';
        entry.textContent = `> ${text}`;
        this.narrativeView.appendChild(entry);
        this.narrativeView.scrollTop = this.narrativeView.scrollHeight;
    }

    _createAiResponseEntry() {
        const entry = document.createElement('div');
        entry.className = 'narrative-entry';
        const p = document.createElement('p');
        p.className = 'narrative-text';
        entry.appendChild(p);
        this.narrativeView.appendChild(entry);
        return { entry, paragraph: p };
    }

    async _processStream(response, entryElement, initialParagraph) {
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let currentParagraph = initialParagraph;

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop(); // Keep the potentially incomplete last line

            for (const line of lines) {
                if (!line.trim()) continue;
                try {
                    const chunk = JSON.parse(line);
                    if (chunk.type === 'insight') {
                        this.dmInsight = chunk.content;
                    } else if (chunk.type === 'narrative_chunk') {
                        let content = chunk.content;
                        // Process content for paragraph breaks
                        while (content.includes('\n\n')) {
                            const [before, after] = content.split('\n\n', 2);
                            currentParagraph.textContent += before;
                            
                            const newP = document.createElement('p');
                            newP.className = 'narrative-text';
                            entryElement.appendChild(newP);
                            currentParagraph = newP; // Switch to the new paragraph
                            content = after;
                        }
                        currentParagraph.textContent += content;
                        this.narrativeView.scrollTop = this.narrativeView.scrollHeight;
                    } else if (chunk.type === 'error') {
                        currentParagraph.textContent = `Error: ${chunk.content}`;
                    }
                } catch (e) {
                    console.error("Failed to parse stream chunk:", line, e);
                }
            }
        }
    }
}
