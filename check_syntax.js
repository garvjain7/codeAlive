const fs = require('fs');
const cp = require('child_process');
const path = require('path');

const staticDir = path.join(__dirname, 'static');
const files = fs.readdirSync(staticDir).filter(f => f.endsWith('.js'));

files.forEach(f => {
  try {
    cp.execSync(`node -c "${path.join(staticDir, f)}"`, { stdio: 'pipe' });
    console.log(`OK: ${f}`);
  } catch (e) {
    console.error(`ERROR in ${f}:`);
    console.error(e.stderr.toString());
  }
});
