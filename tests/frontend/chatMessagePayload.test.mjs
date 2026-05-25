import assert from 'node:assert/strict';
import test from 'node:test';

import {
    buildChatMessageRequest,
    parseStoredChatMessage,
} from '../../app/static/js/chatMessagePayload.js';

test('parses assistant action-card payloads', () => {
    const action = {
        id: 'action-1',
        type: 'restart_deployment',
        target: { name: 'api', namespace: 'default' },
    };
    const parsed = parseStoredChatMessage(JSON.stringify({
        text: 'Queued restart.',
        action,
    }));

    assert.equal(parsed.text, 'Queued restart.');
    assert.deepEqual(parsed.action, action);
    assert.equal(parsed.internal, false);
});

test('builds internal approval follow-up requests', () => {
    assert.deepEqual(
        buildChatMessageRequest('I approved the restart action.', true),
        {
            content: 'I approved the restart action.',
            internal: true,
        },
    );
});

test('marks persisted internal messages as hidden metadata', () => {
    const parsed = parseStoredChatMessage(JSON.stringify({
        text: 'I denied the restart action.',
        internal: true,
    }));

    assert.equal(parsed.text, 'I denied the restart action.');
    assert.equal(parsed.internal, true);
    assert.equal(parsed.action, null);
});
