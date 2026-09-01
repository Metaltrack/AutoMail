require('dotenv').config();

function required(name) {
  const value = process.env[name];
  if (!value) throw new Error(`Missing required environment variable: ${name}`);
  return value;
}

function loadConfig() {
  const port = Number(process.env.PORT || 3000);
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error('PORT must be a valid TCP port number.');
  }

  const smtpPort = Number(process.env.SMTP_PORT || 587);
  if (!Number.isInteger(smtpPort) || smtpPort < 1 || smtpPort > 65535) {
    throw new Error('SMTP_PORT must be a valid TCP port number.');
  }

  return {
    port,
    apiKey: required('NOTIFICATION_API_KEY'),
    smtp: {
      host: required('SMTP_HOST'),
      port: smtpPort,
      secure: String(process.env.SMTP_SECURE).toLowerCase() === 'true',
      auth: { user: required('SMTP_USER'), pass: required('SMTP_PASS') }
    },
    mailFrom: required('MAIL_FROM'),
    adminEmail: required('ADMIN_EMAIL')
  };
}

module.exports = { loadConfig };
