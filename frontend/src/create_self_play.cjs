const fs = require('fs');
const path = require('path');

const srcPath = path.join(__dirname, 'GameBoard.jsx');
const destPath = path.join(__dirname, 'SelfPlayBoard.jsx');

let code = fs.readFileSync(srcPath, 'utf8');

code = code.replace(/export default function GameBoard\(\)/g, "export default function SelfPlayBoard()");
code = code.replace(/player2_name: 'Goopy AI'/g, "player2_name: 'Shogun (P2)'");
code = code.replace(/player\.name === 'Goopy AI'/g, "false");
code = code.replace(/if \(player\?\.name === 'Goopy AI'\) return;/g, "");
code = code.replace(/if \(playerName === 'Goopy AI'\) return;/g, "");
code = code.replace(/if \(promotingPlayer\?\.name === 'Goopy AI'\) return;/g, "");
code = code.replace(/if \(showInfernoDanceTarget\.playerName === 'Goopy AI'\) return;/g, "");
code = code.replace(/if \(showInfernoDanceTarget\?\.playerName === 'Goopy AI'\) return;/g, "");

fs.writeFileSync(destPath, code, 'utf8');
console.log('SelfPlayBoard.jsx created successfully.');
