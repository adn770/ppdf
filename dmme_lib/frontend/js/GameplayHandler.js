// dmme_lib/frontend/js/GameplayHandler.js
export class GameplayHandler {
    constructor() {
        this.gameConfig = null;
        this.narrativeView = document.getElementById('narrative-view');
        this.playerInput = document.getElementById('player-input');
        this.sendCommandBtn = document.getElementById('send-command-btn');
        this.knowledgePanel = document.getElementById('knowledge-panel');
        this.dmInsight = '';

        this._addEventListeners();
    }

    init(gameConfig) {
        this.gameConfig = gameConfig;
        console.log("GameplayHandler initialized with config:", this.gameConfig);

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

        const responseParagraph = this._createAiResponseParagraph();
        try {
            const response = await fetch('/api/game/command', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ command: commandText, config: this.gameConfig }),
            });
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            await this._processStream(response, responseParagraph);
        } catch (error) {
            console.error("Failed to get response from game command API:", error);
            responseParagraph.textContent = "Error: Could not connect to the game server.";
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

    _createAiResponseParagraph() {
        const p = document.createElement('p');
        p.className = 'narrative-text';
        this.narrativeView.appendChild(p);
        return p;
    }

    async _processStream(response, paragraphElement) {
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

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
                        paragraphElement.textContent += chunk.content;
                        this.narrativeView.scrollTop = this.narrativeView.scrollHeight;
                    } else if (chunk.type === 'error') {
                        paragraphElement.textContent = `Error: ${chunk.content}`;
                    }
                } catch (e) {
                    console.error("Failed to parse stream chunk:", line, e);
                }
            }
        }
    }
}
