const TEXT_FIELD = 'text';
const ACTION_FIELD = 'action';
const INTERNAL_FIELD = 'internal';

export function parseStoredChatMessage(rawContent) {
    const fallback = {
        text: String(rawContent ?? ''),
        action: null,
        internal: false,
    };

    try {
        const parsed = JSON.parse(fallback.text);
        if (!parsed || typeof parsed !== 'object' || typeof parsed[TEXT_FIELD] !== 'string') {
            return fallback;
        }

        return {
            text: parsed[TEXT_FIELD],
            action: parsed[ACTION_FIELD] && typeof parsed[ACTION_FIELD] === 'object' ? parsed[ACTION_FIELD] : null,
            internal: parsed[INTERNAL_FIELD] === true,
        };
    } catch (e) {
        return fallback;
    }
}

export function buildChatMessageRequest(content, internal = false) {
    return {
        content,
        internal: internal === true,
    };
}
