// dmme_lib/frontend/js/wizards/ApiHelper.js
import { status } from '../ui.js';

export async function apiCall(url, options = {}) {
    try {
        const response = await fetch(url, options);
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
        }
        if (response.status === 204) { // No Content
            return null;
        }
        return await response.json();
    } catch (error) {
        console.error(`API call to ${url} failed:`, error);
        status.setText(`Error: ${error.message}`, true);
        throw error;
    }
}
