// dmme_lib/frontend/js/GameplayHandler.js
import { apiCall } from './wizards/ApiHelper.js';

export class GameplayHandler {
    constructor() {
        this.gameConfig = null;
        this.narrativeView = document.getElementById('narrative-view');
        this.playerInput = document.getElementById('player-input');
        this.sendCommandBtn = document.getElementById('send-command-btn');
        this.knowledgePanel = document.getElementById('knowledge-panel');
    }

    init(gameConfig) {
        this.gameConfig = gameConfig;
        console.log("GameplayHandler initialized with config:", this.gameConfig);

        this._addEventListeners();
        this._updateKnowledgePanel();
        this.playerInput.focus();
    }

    _addEventListeners() {
        this.sendCommandBtn.addEventListener('click', () => this._sendCommand());

        this.playerInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this._sendCommand();
            }
        });
    }

    _updateKnowledgePanel() {
        let kbHtml = `<span>Rules: <strong>${this.gameConfig.rules}</strong></span>`;
        if (this.gameConfig.mode === 'module') {
            kbHtml += `<span>Module: <strong>${this.gameConfig.module}</strong></span>`;
        } else {
            kbHtml += `<span>Setting: <strong>${this.gameConfig.setting}</strong></span>`;
        }
        this.knowledgePanel.innerHTML = kbHtml;
    }

    async _sendCommand() {
        const commandText = this.playerInput.value.trim();
        if (!commandText) return;

        this._renderPlayerCommand(commandText);
        this.playerInput.value = '';
        this.playerInput.disabled = true;
        this.sendCommandBtn.disabled = true;

        try {
            const response = await apiCall('/api/game/command', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ command: commandText, config: this.gameConfig }),
            });
            this._renderAiResponse(response);
        } catch (error) {
            // Error is already handled by apiCall helper, but we could add more here
            console.error("Failed to get response from game command API.");
        } finally {
            this.playerInput.disabled = false;
            this.sendCommandBtn.disabled = false;
            this.playerInput.focus();
        }
    }

    _renderPlayerCommand(text) {
        const p = document.createElement('p');
        p.className = 'player-command';
        p.textContent = `> ${text}`;
        this.narrativeView.appendChild(p);
        this.narrativeView.scrollTop = this.narrativeView.scrollHeight;
    }

    _renderAiResponse(data) {
        const p = document.createElement('p');
        p.className = 'narrative-text';
        // A more complex renderer would handle different data.type values
        p.textContent = data.content;
        this.narrativeView.appendChild(p);
        this.narrativeView.scrollTop = this.narrativeView.scrollHeight;
    }
}
