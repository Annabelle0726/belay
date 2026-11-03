// SPDX-License-Identifier: AGPL-3.0-only
const fs=require('node:fs'),path=require('node:path');
const root=path.join(__dirname,'..');
let html=fs.readFileSync(path.join(root,'dev-client.html'),'utf8');
html=html.replace('<head>','<head><base href="/">\n<script src="tests/feedback-browser-fixture.js"></script>');
html=html.replace('Development preview','Offline model stub preview');
html=html.replace(/(<script\b[^>]*\bsrc="dev-client\.js(?:\?[^"]*)?"[^>]*>)/, '<script>document.getElementById("backend").value=window.SOL_BACKEND_URL;</script>$1');
const target=path.join(root,'tests','fixtures','generated-feedback-preview.html');
fs.mkdirSync(path.dirname(target),{recursive:true});fs.writeFileSync(target,html);console.log(target);
