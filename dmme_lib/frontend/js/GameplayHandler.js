// dmme_lib/frontend/js/GameplayHandler.js
import { showGameSpinner, hideGameSpinner } from './ui.js';
import { apiCall } from './wizards/ApiHelper.js';

export class GameplayHandler {
    constructor(appInstance, dmInsightInstance) {
        this.app = appInstance;
        this.dmInsight = dmInsightInstance;
        this.gameConfig = null;
        this.narrativeView = document.getElementById('narrative-view');
        this.playerInput = document.getElementById('player-input');
        this.sendCommandBtn = document.getElementById('send-command-btn');
        this.kbDisplay = document.getElementById('kb-display');
        this.partyAccordionContainer = document.getElementById('party-accordion-container');
        this.autosaveInterval = null;
        this.showVisualAids = false;
        this.showAsciiScene = false;
        this.lastInsightContent = '';
        // Toolbar controls
        this.quickThemeSelector = document.getElementById('quick-theme-selector');
        this.fontSizeSlider = document.getElementById('font-size-slider');
        this.lineHeightSlider = document.getElementById('line-height-slider');
        this.toggleVisualAidsBtn = document.getElementById('toggle-visual-aids-btn');
        this.toggleAsciiSceneBtn = document.getElementById('toggle-ascii-scene-btn');
        this.insightToolbarBtn = document.getElementById('dm-insight-btn-toolbar');
        // Image Lightbox elements
        this.lightboxModal = document.getElementById('image-lightbox-modal');
        this.lightboxImage = document.getElementById('image-lightbox-content');
        this.lightboxClose = document.getElementById('image-lightbox-close');

        this._addEventListeners();
    }

    async init(gameConfig, recoveredState = null) {
        this.gameConfig = gameConfig;
        console.log("GameplayHandler initialized with config:", this.gameConfig);

        this._updateKnowledgePanel();
        this._applyInitialStyles();
        this._updateToolbarState();
        await this._populatePartyStatusPanel();

        // Make the main game content visible
        document.getElementById('game-view-content').style.display = 'flex';

        if (recoveredState) {
            this.loadState(recoveredState);
        } else {
            this._startNarration();
        }
        this.startAutosave();
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
        this.toggleVisualAidsBtn.addEventListener('click', () => this._toggleVisualAids());
        this.toggleAsciiSceneBtn.addEventListener('click', () => this._toggleAsciiScene());
        this.insightToolbarBtn.addEventListener('click', () => this._showLastInsight());
        this.lightboxClose.addEventListener('click', () => this._closeLightbox());
    }

    _applyInitialStyles() {
        this.narrativeView.style.fontSize = `${this.fontSizeSlider.value}rem`;
        this.narrativeView.style.lineHeight = this.lineHeightSlider.value;
        this.quickThemeSelector.value = ""; // Reset quick theme selector
        this.insightToolbarBtn.disabled = true;
    }

    async _populatePartyStatusPanel() {
        if (!this.gameConfig || !this.gameConfig.party) return;
        this.partyAccordionContainer.innerHTML = ''; // Clear existing content

        const characters = await apiCall(`/api/parties/${this.gameConfig.party}/characters`);
        characters.forEach(char => {
            const item = document.createElement('div');
            item.className = 'accordion-item';

            const header = document.createElement('button');
            header.className = 'accordion-header';
            header.innerHTML = `
                <span>${char.name} - Lvl ${char.level} ${char.class}</span>
                <span class="accordion-icon">+</span>
            `;

            const body = document.createElement('div');
            body.className = 'accordion-body';
            const stats = Object.keys(char.stats).length > 0
                ? JSON.stringify(char.stats, null, 2)
                : 'No stats provided.';
            body.innerHTML = `
                <p>${char.description || 'No description.'}</p>
                <pre class="char-stats">${stats}</pre>
            `;

            item.appendChild(header);
            item.appendChild(body);
            this.partyAccordionContainer.appendChild(item);
        });
        // Add event listeners to the newly created headers
        this.partyAccordionContainer.querySelectorAll('.accordion-header').forEach(button => {
            button.addEventListener('click', () => {
                const accordionBody = button.nextElementSibling;
                const icon = button.querySelector('.accordion-icon');
                const isActive = accordionBody.classList.contains('active');

                // Optional: Close all other accordions
                this.partyAccordionContainer.querySelectorAll('.accordion-body').forEach(b => {
                    b.classList.remove('active');
                    b.previousElementSibling.querySelector('.accordion-icon').textContent = '+';
                });

                if (!isActive) {
                    accordionBody.classList.add('active');
                    if (icon) icon.textContent = '-';
                }
            });
        });
    }

    _updateToolbarState() {
        this.toggleVisualAidsBtn.classList.toggle('active', this.showVisualAids);
        this.toggleAsciiSceneBtn.classList.toggle('active', this.showAsciiScene);
    }

    _toggleVisualAids() {
        this.showVisualAids = !this.showVisualAids;
        this._updateToolbarState();
    }

    _toggleAsciiScene() {
        this.showAsciiScene = !this.showAsciiScene;
        this._updateToolbarState();
    }

    _applyQuickTheme(event) {
        const themeName = event.target.value;
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
        if (this.gameConfig.llm_model) {
            kbHtml += ` |
 <span>${i18n.t('dmModel')}: <strong>${this.gameConfig.llm_model}</strong></span>`;
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
            if (this.lastInsightContent) {
                this.insightToolbarBtn.disabled = false;
            }
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

        // Create a temporary config for this command including UI state
        const commandConfig = {
            ...this.gameConfig,
            show_visual_aids: this.showVisualAids,
            show_ascii_scene: this.showAsciiScene,
        };
        const { entry, paragraph } = this._createAiResponseEntry();

        try {
            const response = await fetch('/api/game/command', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ command: commandText, config: commandConfig }),
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
            if (this.lastInsightContent) {
                this.insightToolbarBtn.disabled = false;
            }
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

    _showLastInsight() {
        if (!this.lastInsightContent) return;

        const contentBox = this.dmInsight.contentEl;
        contentBox.innerHTML = ''; // Clear previous content

        try {
            const insights = JSON.parse(this.lastInsightContent);
            if (insights.length === 0) {
                const emptyMsg = document.createElement('p');
                emptyMsg.className = 'dm-insight-empty';
                emptyMsg.textContent = this.app.i18n.t('dmInsightEmpty');
                contentBox.appendChild(emptyMsg);
            } else {
                insights.forEach(item => {
                    const chunkDiv = document.createElement('div');
                    chunkDiv.className = 'dm-insight-chunk';

                    const labelSpan = document.createElement('span');
                    labelSpan.className = 'dm-insight-label';
                    labelSpan.textContent = item.label || 'prose';
                    chunkDiv.appendChild(labelSpan);

                    const textPre = document.createElement('pre');
                    textPre.className = 'dm-insight-text';
                    textPre.textContent = item.text;
                    chunkDiv.appendChild(textPre);

                    contentBox.appendChild(chunkDiv);
                });
            }
            this.dmInsight.open();
        } catch (e) {
            console.error("Failed to parse insight JSON:", e);
            // Fallback for non-JSON or malformed content
            contentBox.textContent = this.lastInsightContent;
            this.dmInsight.open();
        }
    }

    _renderCoverMosaic(chunk) {
        const container = document.createElement('div');
        container.className = 'cover-mosaic-container';
        chunk.image_urls.forEach(url => {
            const img = document.createElement('img');
            img.src = url;
            container.appendChild(img);
        });
        this.narrativeView.prepend(container);
    }

    _renderVisualAid(chunk) {
        const figure = document.createElement('figure');
        figure.className = 'narrative-entry visual-aid-container';
        figure.addEventListener('click', () => this._openLightbox(chunk.full_url));

        const img = document.createElement('img');
        img.src = chunk.thumb_url;
        img.alt = chunk.caption;
        img.title = chunk.caption;
        const figcaption = document.createElement('figcaption');
        figcaption.textContent = chunk.caption;

        figure.appendChild(img);
        figure.appendChild(figcaption);

        this.narrativeView.appendChild(figure);
        this.narrativeView.scrollTop = this.narrativeView.scrollHeight;
    }

    _openLightbox(src) {
        this.lightboxImage.src = src;
        this.lightboxModal.style.display = 'block';
    }

    _closeLightbox() {
        this.lightboxModal.style.display = 'none';
        this.lightboxImage.src = '';
    }

    _renderAsciiMap(chunk) {
        const pre = document.createElement('pre');
        pre.className = 'narrative-entry ascii-map-container';
        pre.textContent = chunk.content;
        this.narrativeView.appendChild(pre);
        this.narrativeView.scrollTop = this.narrativeView.scrollHeight;
    }

    async _processStream(response, entryElement, initialParagraph) {
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let currentParagraph = initialParagraph;
        let currentParagraphMarkdown = '';
        this.lastInsightContent = '';
        // Reset for this turn

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();
            // Keep the potentially incomplete last line

            for (const line of lines) {
                if (!line.trim()) continue;
                try {
                    const chunk = JSON.parse(line);
                    if (chunk.type === 'insight') {
                        this.lastInsightContent = chunk.content;
                    } else if (chunk.type === 'cover_mosaic') {
                        this._renderCoverMosaic(chunk);
                    } else if (chunk.type === 'narrative_chunk') {
                        let content = chunk.content;
                        if (content.includes('\n\n')) {
                            const parts = content.split('\n\n');
                            // Finish the current paragraph with the first part
                            currentParagraphMarkdown += parts[0];
                            currentParagraph.innerHTML = window.marked.parse(currentParagraphMarkdown);
                            // Create new paragraphs for the middle parts
                            for (let i = 1; i < parts.length - 1; i++) {
                                const newP = document.createElement('p');
                                newP.className = 'narrative-text';
                                newP.innerHTML = window.marked.parse(parts[i]);
                                entryElement.appendChild(newP);
                            }
                            // Start a new paragraph for the last part
                            const newP = document.createElement('p');
                            newP.className = 'narrative-text';
                            entryElement.appendChild(newP);
                            currentParagraph = newP;
                            currentParagraphMarkdown = parts[parts.length - 1];
                        } else {
                            currentParagraphMarkdown += content;
                        }
                        currentParagraph.innerHTML = window.marked.parse(currentParagraphMarkdown + '▍');
                        this.narrativeView.scrollTop = this.narrativeView.scrollHeight;
                    } else if (chunk.type === 'visual_aid' && this.showVisualAids) {
                        this._renderVisualAid(chunk);
                    } else if (chunk.type === 'ascii_map' && this.showAsciiScene) {
                        this._renderAsciiMap(chunk);
                    } else if (chunk.type === 'error') {
                        currentParagraph.textContent = `Error: ${chunk.content}`;
                    }
                } catch (e) {
                    console.error("Failed to parse stream chunk:", line, e);
                }
            }
        }
        // Final render without the cursor
        currentParagraph.innerHTML = window.marked.parse(currentParagraphMarkdown);
    }

    startAutosave() {
        if (this.autosaveInterval) clearInterval(this.autosaveInterval);
        this.autosaveInterval = setInterval(() => this._performAutosave(), 15000);
        console.log("Autosave interval started.");
    }

    stopAutosave() {
        if (this.autosaveInterval) {
            clearInterval(this.autosaveInterval);
            this.autosaveInterval = null;
            console.log("Autosave interval stopped.");
        }
    }

    endGame() {
        this.stopAutosave();
        this.gameConfig = null;
        console.log("Game session ended and autosave stopped.");
    }

    async _performAutosave() {
        if (!this.gameConfig) {
            console.log("No active game, skipping autosave.");
            return;
        }

        const state = {
            config: this.gameConfig,
            narrativeHTML: this.narrativeView.innerHTML,
        };
        try {
            await fetch('/api/session/autosave', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(state),
                keepalive: true
            });
            console.log("Autosave successful.");
        } catch (error) {
            console.error("Autosave failed:", error);
        }
    }

    loadState(recoveredState) {
        this.narrativeView.innerHTML = recoveredState.narrativeHTML;
        this.narrativeView.scrollTop = this.narrativeView.scrollHeight;
        this.playerInput.disabled = false;
        this.sendCommandBtn.disabled = false;
        this.playerInput.focus();
        hideGameSpinner();
    }
}
