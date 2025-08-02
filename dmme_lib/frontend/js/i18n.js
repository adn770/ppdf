// dmme_lib/frontend/js/i18n.js

class I18nManager {
    constructor() {
        this.translations = {};
        this.currentLang = 'en';
    }

    async init(lang = 'en') {
        this.currentLang = lang;
        await this.loadLanguage(this.currentLang);
        this.translatePage();
    }

    async loadLanguage(lang) {
        try {
            const response = await fetch(`locales/${lang}.json`);
            if (!response.ok) {
                throw new Error(`Failed to load language file: ${lang}.json`);
            }
            this.translations = await response.json();
            document.documentElement.lang = lang; // Update doc lang
        } catch (error) {
            console.error(error);
            // Fallback to English if the selected language fails to load
            if (lang !== 'en') {
                await this.loadLanguage('en');
            }
        }
    }

    async setLanguage(lang) {
        if (lang === this.currentLang) return;
        this.currentLang = lang;
        await this.loadLanguage(lang);
        this.translatePage();
    }

    translatePage() {
        document.querySelectorAll('[data-i18n-key]').forEach(el => {
            const key = el.getAttribute('data-i18n-key');
            const translation = this.t(key);
            if (el.hasAttribute('data-i18n-target')) {
                const target = el.getAttribute('data-i18n-target');
                el.setAttribute(target, translation);
            } else {
                el.textContent = translation;
            }
        });
    }

    t(key, replacements = {}) {
        let translation = this.translations[key] || key;
        for (const placeholder in replacements) {
            translation = translation.replace(`{{${placeholder}}}`, replacements[placeholder]);
        }
        return translation;
    }
}

export const i18n = new I18nManager();
