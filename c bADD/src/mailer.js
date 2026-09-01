const nodemailer = require('nodemailer');

function createMailer(config) {
  return nodemailer.createTransport(config.smtp);
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function createLoginEmails(payload, config) {
  const { userName, userEmail, loginTime, device } = payload;
  const safeName = escapeHtml(userName);
  const safeTime = escapeHtml(loginTime);
  const safeDevice = escapeHtml(device);

  return {
    user: {
      from: config.mailFrom,
      to: userEmail,
      subject: 'New login detected on your account',
      text: `Hi ${userName},\n\nA login was detected on your account.\n\nTime: ${loginTime}\nDevice: ${device}\n\nIf this was not you, please secure your account immediately.`,
      html: `<p>Hi ${safeName},</p><p>A login was detected on your account.</p><ul><li><strong>Time:</strong> ${safeTime}</li><li><strong>Device:</strong> ${safeDevice}</li></ul><p>If this was not you, please secure your account immediately.</p>`
    },
    admin: {
      from: config.mailFrom,
      to: config.adminEmail,
      subject: `Login success: ${userName}`,
      text: `${userName} (${userEmail}) logged in.\n\nTime: ${loginTime}\nDevice: ${device}`,
      html: `<p><strong>${safeName}</strong> (${escapeHtml(userEmail)}) logged in.</p><ul><li><strong>Time:</strong> ${safeTime}</li><li><strong>Device:</strong> ${safeDevice}</li></ul>`
    }
  };
}

module.exports = { createMailer, createLoginEmails };
