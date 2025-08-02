// dmme_lib/frontend/js/components/DiceRoller.js

export class DiceRoller {
    constructor(gameplayHandler) {
        this.gameplayHandler = gameplayHandler;
        this.expression = [];

        this.roller = document.getElementById('dice-roller');
        this.display = document.getElementById('dice-display');

        this.roller.addEventListener('click', (e) => this._handleButton(e));
    }

    _handleButton(event) {
        if (event.target.tagName !== 'BUTTON') return;
        const action = event.target.dataset.action;

        switch (action) {
            case 'roll':
                this._roll();
                break;
            case 'clear':
                this._clearExpression();
                break;
            case 'backspace':
                this._backspace();
                break;
            default:
                this._addToExpression(action);
        }
    }

    _addToExpression(value) {
        if (this.expression.length >= 20) return;

        const lastItem = this.expression.length > 0 ? this.expression[this.expression.length - 1] : null;
        const isDie = (val) => val && val.startsWith('d');
        const isStackedDie = (val) => val && /^\d+d\d+$/.test(val);
        const isOperator = (val) => ['+', '-'].includes(val);
        const isNumeric = (val) => val && /^\d+$/.test(val);

        // Dice stacking logic
        if (isDie(value) && (isDie(lastItem) || isStackedDie(lastItem))) {
            if (lastItem.endsWith(value)) { // e.g., last is 'd6' or '2d6', new is 'd6'
                let count = 1;
                let baseDie = value;
                if(isStackedDie(lastItem)) {
                    count = parseInt(lastItem.split('d')[0], 10);
                }
                this.expression[this.expression.length - 1] = `${count + 1}${baseDie}`;
                this._updateDisplay();
                return;
            }
        }

        // Append digits to existing numbers
        if (isNumeric(value) && isNumeric(lastItem)) {
            this.expression[this.expression.length - 1] = lastItem + value;
            this._updateDisplay();
            return;
        }

        // Prevent invalid sequences
        if (isOperator(value) && (!lastItem || isOperator(lastItem))) return;
        if (!isOperator(value) && lastItem && !isOperator(lastItem)) return;

        this.expression.push(value);
        this._updateDisplay();
    }

    _clearExpression() {
        this.expression = [];
        this._updateDisplay();
    }

    _backspace() {
        if (this.expression.length === 0) return;
        
        let lastItem = this.expression[this.expression.length - 1];
        
        if (/^\d+d\d+$/.test(lastItem)) { // It's a stacked die like '2d6'
            let [count, die] = lastItem.split('d');
            let newCount = parseInt(count, 10) - 1;
            if (newCount > 1) {
                this.expression[this.expression.length - 1] = `${newCount}d${die}`;
            } else {
                this.expression[this.expression.length - 1] = `d${die}`;
            }
        } else if (isNumeric(lastItem) && lastItem.length > 1) {
            this.expression[this.expression.length - 1] = lastItem.slice(0, -1);
        } else {
            this.expression.pop();
        }
        this._updateDisplay();
    }

    _updateDisplay() {
        this.display.textContent = this.expression.join(' ') || '0';
    }

    _parseAndRoll(expressionStr) {
        const cleanExpression = expressionStr.replace(/\s+/g, '');
        if (!/^(\d*d\d+|[+-]|\d+)+$/.test(cleanExpression)) {
            return { total: null, details: "Invalid expression" };
        }

        const terms = cleanExpression.match(/([+-]?)(\d*d\d+|\d+)/g) || [];
        let total = 0;
        const details = [];

        for (const term of terms) {
            const sign = term.startsWith('-') ? -1 : 1;
            const unsignedTerm = term.replace(/^[+-]/, '');
            let termTotal = 0;

            if (unsignedTerm.includes('d')) {
                let [numDice, numSides] = unsignedTerm.split('d');
                numDice = numDice ? parseInt(numDice, 10) : 1;
                numSides = parseInt(numSides, 10);
                const rolls = [];
                for (let i = 0; i < numDice; i++) {
                    const roll = Math.floor(Math.random() * numSides) + 1;
                    rolls.push(roll);
                    termTotal += roll;
                }
                details.push(`${unsignedTerm}${JSON.stringify(rolls)}`);
            } else {
                termTotal = parseInt(unsignedTerm, 10);
                details.push(unsignedTerm);
            }
            total += termTotal * sign;
        }
        
        let detailsStr = details.join(' ').replace(/\s/g, ' ');
        const finalDetails = detailsStr.split(' ').map((part, i) => {
            if (i > 0) {
                const correspondingTerm = terms.find(t => t.includes(part.split('[')[0]));
                if (correspondingTerm && correspondingTerm.startsWith('-')) {
                    return `- ${part}`;
                }
                return `+ ${part}`;
            }
            return part.replace(/^[+-]/, '');
        }).join(' ');

        return { total, details: finalDetails };
    }


    _roll() {
        if (this.expression.length === 0) return;
        const expressionStr = this.expression.join('');
        const result = this._parseAndRoll(expressionStr);

        let command;
        if (result.total !== null) {
            command = `roll ${expressionStr} (Result: ${result.total}) [${result.details}]`;
        } else {
            command = `attempted to roll invalid expression: ${expressionStr}`;
        }
        
        this.gameplayHandler.submitCommand(command);
        this._clearExpression();
    }
}
