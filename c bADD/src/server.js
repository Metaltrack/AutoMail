const { loadConfig } = require('./config');
const { createMailer } = require('./mailer');
const { createApp } = require('./app');

function start() {
  const config = loadConfig();
  const mailer = createMailer(config);
  const app = createApp({ config, mailer });

  const server = app.listen(config.port, () => {
    console.log(`Notification Service listening on port ${config.port}`);
  });

  function shutdown(signal) {
    console.log(`${signal} received; closing server.`);
    server.close(() => process.exit(0));
  }
  process.on('SIGINT', () => shutdown('SIGINT'));
  process.on('SIGTERM', () => shutdown('SIGTERM'));
}

try {
  start();
} catch (error) {
  console.error(`Unable to start Notification Service: ${error.message}`);
  process.exit(1);
}
