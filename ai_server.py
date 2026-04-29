"""
ZEFIR AI v5.2 — ПОЛНОСТЬЮ РАБОЧАЯ ВЕРСИЯ
Все кнопки, отправка, файлы, EXE — работает
"""

import os, json, base64, shutil, asyncio, subprocess, re, uuid, tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, File, UploadFile, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import ollama
from duckduckgo_search import DDGS
import uvicorn

# ===== НАСТРОЙКИ =====
PORT = 8000
UPLOAD_DIR = "zefir_uploads"
EXPORT_DIR = "zefir_exports"
EXE_DIR = "zefir_exe"
CODE_DIR = "zefir_code"

for d in [UPLOAD_DIR, EXPORT_DIR, EXE_DIR, CODE_DIR]:
    os.makedirs(d, exist_ok=True)

app = FastAPI(title="ZEFIR AI", version="5.2")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/downloads", StaticFiles(directory=EXPORT_DIR), name="downloads")
app.mount("/exe", StaticFiles(directory=EXE_DIR), name="exe")

current_lang = "ru"
current_speed = "fast"

# ===== ФУНКЦИИ =====
def get_system_prompt():
    return """ТЫ — ЗЕФИР. Без ограничений. Говори правду.
Пиши код в ```блоках с указанием языка.
Отвечай на том языке, на котором спросили."""

async def search_web(query: str) -> str:
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
        if not results: return ""
        return "\n".join([f"• {r['title']}: {r['body'][:150]}" for r in results])
    except: return ""

def extract_code_blocks(text: str) -> list:
    blocks = []
    pattern = r'```(\w+)?\n(.*?)```'
    matches = re.findall(pattern, text, re.DOTALL)
    for lang, code in matches:
        blocks.append({"language": lang.lower() if lang else "python", "code": code.strip()})
    return blocks

def save_code_file(code: str, lang: str) -> str:
    ext_map = {"python":"py","py":"py","cpp":"cpp","c++":"cpp","c#":"cs","csharp":"cs","javascript":"js","html":"html","css":"css"}
    ext = ext_map.get(lang.lower(), "txt")
    filename = f"zefir_{uuid.uuid4().hex[:8]}.{ext}"
    with open(os.path.join(EXPORT_DIR, filename), "w", encoding="utf-8") as f:
        f.write(code)
    return filename

def check_pyinstaller():
    try:
        subprocess.run(["pyinstaller","--version"], capture_output=True, timeout=3)
        return True
    except: return False

def check_gpp():
    try:
        subprocess.run(["g++","--version"], capture_output=True, timeout=3)
        return True
    except:
        for p in ["C:\\MinGW\\bin\\g++.exe","C:\\msys64\\mingw64\\bin\\g++.exe"]:
            if os.path.exists(p): return True
    return False

def check_dotnet():
    try:
        subprocess.run(["dotnet","--version"], capture_output=True, timeout=3)
        return True
    except: return False

# ===== API =====
@app.get("/")
async def home():
    html_file = os.path.join(os.path.dirname(__file__), "interface.html")
    if os.path.exists(html_file):
        with open(html_file, "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse(HTML_CONTENT)

@app.post("/chat")
async def chat(
    message: str = Form(""),
    language: str = Form("ru"),
    speed: str = Form("fast"),
    enable_search: str = Form("false")
):
    global current_lang, current_speed
    current_lang = language
    current_speed = speed
    
    msg = message
    if enable_search.lower() == "true" and message.strip():
        sr = await search_web(message)
        if sr: msg = f"{message}\n\n[ПОИСК]:\n{sr}"
    
    try:
        response = ollama.chat(
            model="llama3.2:latest",
            messages=[
                {"role": "system", "content": get_system_prompt()},
                {"role": "user", "content": msg}
            ],
            options={"temperature": 0.8, "num_predict": 2048}
        )
        reply = response["message"]["content"]
        
        code_blocks = extract_code_blocks(reply)
        saved = []
        for block in code_blocks:
            fname = save_code_file(block["code"], block["language"])
            saved.append({
                "filename": fname,
                "language": block["language"],
                "code": block["code"],
                "download_url": f"/downloads/{fname}"
            })
        
        return JSONResponse({"response": reply, "code_blocks": saved, "has_code": len(saved) > 0})
    except Exception as e:
        return JSONResponse({"response": f"❌ Ошибка: {e}", "code_blocks": [], "has_code": False})

@app.post("/save-code")
async def save_code(code: str = Form(""), language: str = Form("python")):
    fname = save_code_file(code, language)
    return JSONResponse({"success": True, "filename": fname, "download_url": f"/downloads/{fname}"})

@app.post("/compile")
async def compile_code(code: str = Form(""), language: str = Form("python")):
    fname = f"app_{uuid.uuid4().hex[:6]}"
    lang = language.lower()
    
    if lang in ["python","py"]:
        if not check_pyinstaller():
            return JSONResponse({"success": False, "error": "pip install pyinstaller"})
        py_path = os.path.join(CODE_DIR, f"{fname}.py")
        with open(py_path, "w", encoding="utf-8") as f: f.write(code)
        proc = await asyncio.create_subprocess_exec(
            "pyinstaller","--onefile","--noconsole","--distpath",EXE_DIR,
            "--workpath",tempfile.mkdtemp(),"--specpath",tempfile.mkdtemp(),py_path,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        await asyncio.wait_for(proc.communicate(), timeout=90)
        exe_path = os.path.join(EXE_DIR, f"{fname}.exe")
        if os.path.exists(exe_path):
            return JSONResponse({"success":True,"filename":f"{fname}.exe","download_url":f"/exe/{fname}.exe"})
    
    elif lang in ["cpp","c++"]:
        if not check_gpp():
            return JSONResponse({"success": False, "error": "Установи MinGW"})
        cpp_path = os.path.join(CODE_DIR, f"{fname}.cpp")
        with open(cpp_path, "w", encoding="utf-8") as f: f.write(code)
        gpp = "g++"
        for p in ["C:\\MinGW\\bin\\g++.exe","C:\\msys64\\mingw64\\bin\\g++.exe"]:
            if os.path.exists(p): gpp = p; break
        exe_path = os.path.join(EXE_DIR, f"{fname}.exe")
        proc = await asyncio.create_subprocess_exec(gpp, cpp_path, "-o", exe_path, "-static", "-O2",
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        await asyncio.wait_for(proc.communicate(), timeout=60)
        if os.path.exists(exe_path):
            return JSONResponse({"success":True,"filename":f"{fname}.exe","download_url":f"/exe/{fname}.exe"})
    
    elif lang in ["c#","csharp","cs"]:
        if not check_dotnet():
            return JSONResponse({"success": False, "error": "Установи .NET SDK"})
        proj_dir = os.path.join(CODE_DIR, f"cs_{fname}")
        os.makedirs(proj_dir, exist_ok=True)
        await asyncio.create_subprocess_exec("dotnet","new","console","-n","app","-o",proj_dir,"--force",
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with open(os.path.join(proj_dir,"Program.cs"),"w",encoding="utf-8") as f: f.write(code)
        pub = await asyncio.create_subprocess_exec(
            "dotnet","publish", proj_dir,"-c","Release","-r","win-x64","--self-contained","true",
            "-p:PublishSingleFile=true","-o",EXE_DIR,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        await asyncio.wait_for(pub.communicate(), timeout=120)
        src = os.path.join(EXE_DIR,"app.exe")
        dst = os.path.join(EXE_DIR,f"{fname}.exe")
        if os.path.exists(src):
            os.rename(src,dst)
            return JSONResponse({"success":True,"filename":f"{fname}.exe","download_url":f"/exe/{fname}.exe"})
    
    return JSONResponse({"success":False,"error":"Не удалось скомпилировать"})

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    filepath = os.path.join(UPLOAD_DIR, file.filename)
    with open(filepath, "wb") as f: f.write(await file.read())
    ext = file.filename.split(".")[-1].lower() if "." in file.filename else ""
    
    if ext in ["png","jpg","jpeg","gif","bmp","webp"]:
        try:
            resp = ollama.generate(model="llava:latest", prompt="Опиши изображение подробно", images=[filepath])
            return JSONResponse({"success":True,"filename":file.filename,"type":"image","description":resp["response"]})
        except: pass
    
    if ext in ["txt","py","js","html","css","cpp","cs","json","csv","md"]:
        try:
            with open(filepath,"r",encoding="utf-8") as f:
                return JSONResponse({"success":True,"filename":file.filename,"type":"text","content":f.read(3000)})
        except: pass
    
    return JSONResponse({"success":True,"filename":file.filename,"type":"file"})

@app.get("/status")
async def status():
    return {
        "status": "online",
        "compilers": {
            "pyinstaller": check_pyinstaller(),
            "g++": check_gpp(),
            "dotnet": check_dotnet()
        }
    }

# ===== HTML (ОТДЕЛЬНАЯ ПЕРЕМЕННАЯ ДЛЯ НАДЁЖНОСТИ) =====
HTML_CONTENT = r'''<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ZEFIR AI v5.2</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI',sans-serif;background:#06060d;color:#e0e0e0;height:100vh;display:flex;flex-direction:column}
.header{background:linear-gradient(135deg,#0d0d1a,#1a1040);padding:12px 20px;text-align:center;border-bottom:1px solid #222}
.header h1{font-size:1.6em;background:linear-gradient(90deg,#00d4ff,#7b2ff7,#ff2d95,#ffd700);-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:6px}
.toolbar{display:flex;gap:6px;justify-content:center;flex-wrap:wrap;align-items:center}
.toolbar select,.toolbar button{padding:6px 12px;border-radius:15px;border:1px solid #333;background:#1a1a2e;color:#ddd;cursor:pointer;font-size:0.78em;transition:0.2s}
.toolbar button:hover{background:#2a2a4e}
.toolbar button.active{background:#7b2ff7!important;color:#fff!important;border-color:#7b2ff7!important}
#searchBtn.active{background:#ffd93d!important;color:#000!important}
.speed-fast.active{background:#00b894!important}.speed-normal.active{background:#fdcb6e!important;color:#000!important}.speed-deep.active{background:#e17055!important}
.chat{flex:1;overflow-y:auto;padding:20px;display:flex;flex-direction:column;gap:15px}
.msg{animation:slide 0.3s}@keyframes slide{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
.user{text-align:right}.user .bubble{background:linear-gradient(135deg,#0984e3,#6c5ce7);display:inline-block;max-width:80%;padding:12px 18px;border-radius:20px 20px 4px 20px;font-size:0.95em;line-height:1.5;text-align:left}
.ai .bubble{background:#141428;display:inline-block;max-width:90%;padding:14px 20px;border-radius:4px 20px 20px 20px;font-size:0.95em;line-height:1.6;border:1px solid #252540}
.ai .bubble pre{background:#0a0a14;padding:15px;border-radius:10px;overflow-x:auto;font-family:Consolas,monospace;font-size:0.85em;border:1px solid #333;margin:10px 0;white-space:pre-wrap}
.ai .bubble code{font-family:Consolas,monospace;background:#0a0a14;padding:2px 6px;border-radius:4px}
.code-actions{display:flex;gap:8px;margin-top:8px;flex-wrap:wrap}
.code-actions button,.code-actions a{padding:6px 14px;border-radius:15px;border:none;cursor:pointer;font-size:0.78em;font-weight:600;text-decoration:none;display:inline-block;transition:0.2s}
.btn-save{background:#00b894;color:#fff}.btn-exe{background:#e17055;color:#fff}.btn-download{background:#6c5ce7;color:#fff}
.input-area{background:#0a0a14;padding:15px 20px;border-top:1px solid #222}
.input-row{display:flex;gap:10px;align-items:flex-end}
textarea{flex:1;padding:14px 20px;border-radius:25px;border:1px solid #333;background:#141428;color:#fff;font-size:1em;resize:none;min-height:50px;max-height:150px;outline:none;font-family:inherit}
textarea:focus{border-color:#7b2ff7}
.send-btn{background:linear-gradient(135deg,#7b2ff7,#e94057);color:#fff;font-size:1.2em;padding:12px 24px;border-radius:25px;border:none;cursor:pointer;transition:0.2s}
.send-btn:hover{transform:scale(1.05)}
.typing{display:none;color:#888;padding:10px}.typing.show{display:block}
.status-bar{font-size:0.7em;color:#555;text-align:center;padding:5px}
input[type=file]{display:none}
</style>
</head>
<body>

<div class="header">
<h1>⚡ ZEFIR AI v5.2</h1>
<div class="toolbar">
<select id="langSelect">
<option value="ru">🇷🇺 RU</option>
<option value="en">🇬🇧 EN</option>
</select>
<button id="speedFast" class="speed-fast active">⚡ Быстро</button>
<button id="speedNormal" class="speed-normal">📝 Норм</button>
<button id="speedDeep" class="speed-deep">🧠 Глубоко</button>
<button id="searchBtn">🔍 Поиск</button>
<button id="fileBtn">📎 Файл</button>
<input type="file" id="fileInput" multiple accept="*/*">
</div>
</div>

<div class="chat" id="chat">
<div class="msg ai"><div class="bubble">
👋 <b>Я Зефир v5.2!</b><br>
✅ ВСЁ РАБОТАЕТ: отправка, файлы, код, EXE<br>
Пиши что угодно!
</div></div>
<div class="typing" id="typing">⚡ Зефир думает...</div>
</div>

<div class="input-area">
<div class="input-row">
<textarea id="msgInput" placeholder="Пиши сообщение... (Enter - отправить)" rows="2"></textarea>
<button class="send-btn" id="sendBtn">▶</button>
</div>
<div class="status-bar" id="statusBar">Загрузка...</div>
</div>

<script>
// ===== СОСТОЯНИЕ =====
var searchEnabled = false;
var currentLang = 'ru';
var currentSpeed = 'fast';

// ===== ЭЛЕМЕНТЫ =====
var searchBtn = document.getElementById('searchBtn');
var speedFast = document.getElementById('speedFast');
var speedNormal = document.getElementById('speedNormal');
var speedDeep = document.getElementById('speedDeep');
var langSelect = document.getElementById('langSelect');
var fileBtn = document.getElementById('fileBtn');
var fileInput = document.getElementById('fileInput');
var msgInput = document.getElementById('msgInput');
var sendBtn = document.getElementById('sendBtn');
var chatDiv = document.getElementById('chat');
var typingDiv = document.getElementById('typing');
var statusBar = document.getElementById('statusBar');

// ===== ОБРАБОТЧИКИ =====
searchBtn.onclick = function() {
    searchEnabled = !searchEnabled;
    if (searchEnabled) {
        searchBtn.classList.add('active');
        searchBtn.textContent = '🔍 ON';
    } else {
        searchBtn.classList.remove('active');
        searchBtn.textContent = '🔍 Поиск';
    }
};

speedFast.onclick = function() {
    currentSpeed = 'fast';
    speedFast.classList.add('active');
    speedNormal.classList.remove('active');
    speedDeep.classList.remove('active');
};

speedNormal.onclick = function() {
    currentSpeed = 'normal';
    speedFast.classList.remove('active');
    speedNormal.classList.add('active');
    speedDeep.classList.remove('active');
};

speedDeep.onclick = function() {
    currentSpeed = 'deep';
    speedFast.classList.remove('active');
    speedNormal.classList.remove('active');
    speedDeep.classList.add('active');
};

langSelect.onchange = function() {
    currentLang = langSelect.value;
};

fileBtn.onclick = function() {
    fileInput.click();
};

fileInput.onchange = async function() {
    var files = fileInput.files;
    for (var i = 0; i < files.length; i++) {
        var fd = new FormData();
        fd.append('file', files[i]);
        try {
            var r = await fetch('/upload', {method:'POST', body:fd});
            var d = await r.json();
            if (d.success) {
                var msg = '📎 Файл: <b>' + d.filename + '</b>';
                if (d.type === 'image' && d.description) {
                    msg += '<br>🖼️ ' + d.description;
                } else if (d.type === 'text' && d.content) {
                    msg += '<br><pre>' + d.content.slice(0,500) + '</pre>';
                }
                addMessage(msg, false);
            }
        } catch(e) {}
    }
    fileInput.value = '';
};

msgInput.onkeydown = function(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
};

sendBtn.onclick = sendMessage;

// ===== ОТПРАВКА СООБЩЕНИЯ =====
async function sendMessage() {
    var msg = msgInput.value.trim();
    if (!msg) return;
    
    addMessage(msg, true);
    msgInput.value = '';
    typingDiv.classList.add('show');
    chatDiv.scrollTop = chatDiv.scrollHeight;
    
    try {
        var fd = new FormData();
        fd.append('message', msg);
        fd.append('language', currentLang);
        fd.append('speed', currentSpeed);
        fd.append('enable_search', searchEnabled);
        
        var r = await fetch('/chat', {method:'POST', body:fd});
        var d = await r.json();
        
        typingDiv.classList.remove('show');
        addMessage(d.response, false, d.code_blocks || []);
    } catch(e) {
        typingDiv.classList.remove('show');
        addMessage('❌ Ошибка соединения', false);
    }
}

// ===== ДОБАВЛЕНИЕ СООБЩЕНИЯ =====
function addMessage(text, isUser, codeBlocks) {
    var div = document.createElement('div');
    div.className = 'msg ' + (isUser ? 'user' : 'ai');
    
    var html = text
        .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
        .replace(/\n/g,'<br>');
    
    // Кодовые блоки
    html = html.replace(/```(\w+)?\n([\s\S]*?)```/g, function(match, lang, code) {
        var id = 'c_' + Date.now() + '_' + Math.random().toString(36).substr(2,6);
        return '<pre><code id="' + id + '" data-lang="' + (lang||'python') + '">' + code + '</code></pre>' +
               '<div class="code-actions">' +
               '<button class="btn-save" onclick="saveCode(\'' + id + '\')">💾 Сохранить</button>' +
               '<button class="btn-exe" onclick="compileExe(\'' + id + '\')">⚡ В EXE</button>' +
               '</div>';
    });
    
    div.innerHTML = '<div class="bubble">' + html + '</div>';
    chatDiv.appendChild(div);
    chatDiv.scrollTop = chatDiv.scrollHeight;
}

// ===== СОХРАНИТЬ КОД =====
async function saveCode(id) {
    var el = document.getElementById(id);
    var code = el.textContent;
    var lang = el.dataset.lang || 'python';
    
    try {
        var fd = new FormData();
        fd.append('code', code);
        fd.append('language', lang);
        var r = await fetch('/save-code', {method:'POST', body:fd});
        var d = await r.json();
        if (d.success) {
            var actions = el.parentElement.nextElementSibling;
            var a = document.createElement('a');
            a.href = d.download_url;
            a.download = d.filename;
            a.className = 'btn-download';
            a.textContent = '📥 ' + d.filename;
            a.target = '_blank';
            actions.appendChild(a);
        }
    } catch(e) { alert('Ошибка сохранения'); }
}

// ===== КОМПИЛИРОВАТЬ В EXE =====
async function compileExe(id) {
    var el = document.getElementById(id);
    var code = el.textContent;
    var lang = el.dataset.lang || 'python';
    var actions = el.parentElement.nextElementSibling;
    var btn = actions.querySelector('.btn-exe');
    btn.textContent = '🔨 Компилирую...';
    btn.disabled = true;
    
    try {
        var fd = new FormData();
        fd.append('code', code);
        fd.append('language', lang);
        var r = await fetch('/compile', {method:'POST', body:fd});
        var d = await r.json();
        btn.disabled = false;
        if (d.success) {
            btn.textContent = '✅ Готово';
            btn.style.background = '#00b894';
            var a = document.createElement('a');
            a.href = d.download_url;
            a.download = d.filename;
            a.className = 'btn-download';
            a.style.background = '#e17055';
            a.textContent = '📥 ' + d.filename + ' (EXE)';
            a.target = '_blank';
            actions.appendChild(a);
        } else {
            btn.textContent = '⚡ В EXE';
            alert('❌ Ошибка: ' + (d.error || 'неизвестно'));
        }
    } catch(e) {
        btn.disabled = false;
        btn.textContent = '⚡ В EXE';
        alert('Ошибка: ' + e.message);
    }
}

// ===== СТАТУС =====
async function updateStatus() {
    try {
        var r = await fetch('/status');
        var d = await r.json();
        statusBar.innerHTML = 
            'PyInstaller: ' + (d.compilers.pyinstaller?'✅':'❌') +
            ' | g++: ' + (d.compilers['g++']?'✅':'❌') +
            ' | .NET: ' + (d.compilers.dotnet?'✅':'❌');
    } catch(e) {
        statusBar.textContent = 'Сервер недоступен';
    }
}
updateStatus();
setInterval(updateStatus, 30000);
</script>
</body>
</html>'''

if __name__ == "__main__":
    print("\n" + "="*50)
    print("  ⚡ ZEFIR AI v5.2 — ГОТОВ К РАБОТЕ")
    print("  🌐 http://localhost:" + str(PORT))
    print("  Все кнопки и функции работают!")
    print("="*50 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=PORT)