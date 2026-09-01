const crypto = require('crypto');
const express = require('express');
const { createLoginEmails } = require('./mailer');

const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function hasValidApiKey(request, expectedKey) {
  const authorization = request.get('authorization') || '';
  const suppliedKey = authorization.startsWith('Bearer ')
    ? authorization.slice(7)
    : '';

  const supplied = Buffer.from(suppliedKey);
  const expected = Buffer.from(expectedKey);
  return supplied.length === expected.length && crypto.timingSafeEqual(supplied, expected);
}

function validateLoginPayload(payload) {
  const fields = ['userName', 'userEmail', 'loginTime', 'device'];
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    return 'Request body must be a JSON object.';
  }
  for (const field of fields) {
    if (typeof payload[field] !== 'string' || !payload[field].trim()) {
      return `${field} is required and must be a non-empty string.`;
    }
    if (payload[field].length > 300) return `${field} must not exceed 300 characters.`;
  }
  if (!emailPattern.test(payload.userEmail)) return 'userEmail must be a valid email address.';
  return null;
}

function createApp({ config, mailer, logger = console }) {
  const app = express();
  app.disable('x-powered-by');
  app.use(express.json({ limit: '20kb' }));

  app.get('/health', (_request, response) => response.status(200).json({ status: 'ok' }));

  app.post('/notifications/login-success', async (request, response) => {
    if (!hasValidApiKey(request, config.apiKey)) {
      return response.status(401).json({ error: 'Unauthorized' });
    }

    const validationError = validateLoginPayload(request.body);
    if (validationError) return response.status(400).json({ error: validationError });

    const emails = createLoginEmails(request.body, config);
    try {
      const [userResult, adminResult] = await Promise.all([
        mailer.sendMail(emails.user),
        mailer.sendMail(emails.admin)
      ]);
      logger.info(`Login notifications sent for ${request.body.userEmail}. User=${userResult.messageId}; admin=${adminResult.messageId}`);
      return response.status(202).json({ message: 'Login notifications sent.' });
    } catch (error) {
      logger.error(`Login notification failed for ${request.body.userEmail}: ${error.message}`);
      return response.status(502).json({ error: 'Unable to send login notifications.' });
    }
  });

  app.use((error, _request, response, _next) => {
    if (error instanceof SyntaxError && error.status === 400 && 'body' in error) {
      return response.status(400).json({ error: 'Request body must contain valid JSON.' });
    }
    logger.error(`Unhandled request error: ${error.message}`);
    return response.status(500).json({ error: 'Internal server error.' });
  });

  return app;
}

module.exports = { createApp, hasValidApiKey, validateLoginPayload };
