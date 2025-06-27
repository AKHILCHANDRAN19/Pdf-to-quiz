import fitz  # PyMuPDF
import re
import os
import uuid
from flask import Flask, request, redirect, url_for, render_template_string, session, jsonify, flash
from werkzeug.utils import secure_filename

# --- Configuration ---
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf'}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['SECRET_KEY'] = 'a_final_and_very_secure_key'

# Server-side storage for quizzes
QUIZ_SESSIONS = {}

# --- Helper Function (Restored) ---
def allowed_file(filename):
    """Checks if the uploaded file has a .pdf extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Robust PDF Parsing Logic ---
def parse_questions_from_pdf(pdf_path):
    print(f"Starting robust parsing for PDF: '{pdf_path}'...")
    full_text = ""
    try:
        with fitz.open(pdf_path) as doc:
            for page in doc:
                full_text += page.get_text("text") + "\n"
    except Exception as e:
        print(f"Error reading PDF: {e}")
        return []

    full_text = full_text.replace('*', '').replace('\r\n', '\n')
    lines = full_text.split('\n')
    questions = []
    current_question = None
    capture_stage = None
    q_start_pattern = re.compile(r'ചോദ്യം\s*(\d+)\.(.*)')
    options_marker = re.compile(r'ഓപ്ഷനുകൾ:')
    answer_marker = re.compile(r'ഉത്തരം:')
    option_pattern = re.compile(r'([A-D])\)\s*(.*)')

    for line in lines:
        line = line.strip()
        if not line:
            continue

        q_match = q_start_pattern.match(line)
        if q_match:
            if current_question and 'options' in current_question and 'correct_answer' in current_question:
                questions.append(current_question)
            
            q_num = int(q_match.group(1))
            q_text = q_match.group(2).strip()
            current_question = {"number": q_num, "question": q_text, "options": {}}
            capture_stage = 'question'
            continue

        if current_question:
            if options_marker.match(line):
                capture_stage = 'options'
                continue
            
            if answer_marker.match(line):
                capture_stage = 'answer'
                ans_match = re.search(r'[A-D]', line.split(':')[-1])
                if ans_match:
                    current_question['correct_answer'] = ans_match.group(0)
                continue

            if capture_stage == 'question':
                current_question['question'] += ' ' + line
            elif capture_stage == 'options':
                opt_match = option_pattern.match(line)
                if opt_match:
                    key, val = opt_match.groups()
                    current_question['options'][key] = val.strip()
                elif current_question['options']:
                    # This handles multi-line options
                    last_key = list(current_question['options'].keys())[-1]
                    current_question['options'][last_key] += ' ' + line
            elif capture_stage == 'answer':
                if 'correct_answer' not in current_question:
                    ans_match = re.search(r'[A-D]', line)
                    if ans_match:
                        current_question['correct_answer'] = ans_match.group(0)

    if current_question and 'options' in current_question and 'correct_answer' in current_question:
        questions.append(current_question)
    
    questions.sort(key=lambda x: x['number'])
    print(f"Successfully parsed {len(questions)} questions.")
    return questions

# --- HTML Templates (Generic Titles & Dynamic Quiz Name) ---

UPLOAD_TEMPLATE = """
<!DOCTYPE html><html lang="ml"><head><meta charset="UTF-8"><title>PDF ക്വിസ് ആപ്പ്</title><meta name="viewport" content="width=device-width, initial-scale=1.0"><style>@import url('https://fonts.googleapis.com/css2?family=Manjari:wght@400;700&family=Noto+Sans+Malayalam:wght@400;700&display=swap');body{font-family:'Noto Sans Malayalam','Manjari',sans-serif;background:linear-gradient(135deg,#43cea2,#185a9d);display:flex;justify-content:center;align-items:center;height:100vh;margin:0;color:#fff;overflow:hidden}.container{background:rgba(255,255,255,0.98);padding:50px;border-radius:20px;box-shadow:0 15px 35px rgba(0,0,0,0.2);text-align:center;max-width:550px;width:90%;color:#333;transform:translateY(-20px);animation:fade-in .6s ease-out forwards}h1{color:#185a9d;font-weight:700;font-size:2.5em;margin-bottom:15px}p{color:#555;font-size:1.1em;margin-bottom:30px}.upload-area{border:3px dashed #ccc;border-radius:15px;padding:40px;margin-top:20px;cursor:pointer;transition:all .3s ease}.upload-area:hover{border-color:#43cea2;background-color:#f9f9f9;transform:scale(1.02)}.upload-area i{font-size:3em;color:#43cea2;margin-bottom:15px}.upload-area p{margin:0;font-size:1em;color:#7f8c8d}input[type=file]{display:none}.upload-button{background:linear-gradient(45deg,#185a9d,#43cea2);color:#fff;border:none;padding:18px 35px;border-radius:10px;font-size:1.2em;cursor:pointer;transition:all .3s ease;margin-top:25px;width:100%;font-weight:700;box-shadow:0 4px 15px rgba(0,0,0,0.2)}.upload-button:hover{transform:translateY(-3px);box-shadow:0 6px 20px rgba(0,0,0,0.3)}.flash-message{padding:15px;margin-bottom:20px;border-radius:8px;color:#721c24;background-color:#f8d7da;border:1px solid #f5c6cb}@keyframes fade-in{from{opacity:0;transform:translateY(20px)}to{opacity:1;transform:translateY(0)}}</style><link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.3/css/all.min.css"></head><body><div class="container"><h1>PDF ക്വിസ് ആപ്പ്</h1><p>നിങ്ങളുടെ അറിവ് പരീക്ഷിക്കാൻ ഒരു PDF ഫയൽ അപ്‌ലോഡ് ചെയ്യുക</p>{% with messages=get_flashed_messages() %}{% if messages %}<div class=flash-message>{{ messages[0] }}</div>{% endif %}{% endwith %}<form action="{{ url_for('upload_file') }}" method=post enctype=multipart/form-data id=upload-form><div class=upload-area onclick="document.getElementById('file-input').click();"><i class="fas fa-file-pdf"></i><p id=upload-text>ചോദ്യങ്ങളടങ്ങിയ PDF ഫയൽ ഇവിടെ തിരഞ്ഞെടുക്കുക</p></div><input type=file name=pdf_file id=file-input accept=.pdf><button type=submit class=upload-button>അപ്‌ലോഡ് ചെയ്ത് തുടങ്ങുക</button></form></div><script>const fileInput=document.getElementById("file-input"),uploadText=document.getElementById("upload-text");fileInput.addEventListener("change",(()=>{fileInput.files.length>0?uploadText.textContent=`ഫയൽ: ${fileInput.files[0].name}`:uploadText.textContent="ചോദ്യങ്ങളടങ്ങിയ PDF ഫയൽ ഇവിടെ തിരഞ്ഞെടുക്കുക"}));</script></body></html>
"""

SELECT_RANGE_TEMPLATE = """
<!DOCTYPE html><html lang="ml"><head><meta charset="UTF-8"><title>ചോദ്യങ്ങൾ തിരഞ്ഞെടുക്കുക</title><meta name="viewport" content="width=device-width, initial-scale=1.0"><style>@import url('https://fonts.googleapis.com/css2?family=Manjari:wght@400;700&family=Noto+Sans+Malayalam:wght@400;700&display=swap');body{font-family:'Noto Sans Malayalam','Manjari',sans-serif;background:linear-gradient(135deg,#f0f2f5,#e6e9f0);display:flex;justify-content:center;align-items:center;height:100vh;margin:0;color:#333}.container{background:#fff;padding:50px;border-radius:20px;box-shadow:0 15px 35px rgba(0,0,0,0.1);text-align:center;max-width:600px;width:90%;animation:pop-in .5s cubic-bezier(.175,.885,.32,1.275)}h1{color:#34495e;font-size:2em;margin-bottom:10px}p{color:#7f8c8d;margin-bottom:30px;font-size:1.2em}span.total-q{font-weight:700;color:#27ae60;font-size:1.5em}.form-group{margin:30px 0;display:flex;justify-content:space-around;align-items:center}label{font-weight:700;color:#34495e;font-size:1.1em}input{padding:12px;border:2px solid #bdc3c7;border-radius:10px;width:100px;text-align:center;font-size:1.1em;transition:all .3s ease}input:focus{outline:0;border-color:#3498db;box-shadow:0 0 8px rgba(52,152,219,.3)}.start-button{background:linear-gradient(45deg,#3498db,#2980b9);color:#fff;border:none;padding:18px 35px;border-radius:10px;font-size:1.2em;cursor:pointer;transition:all .3s ease;font-weight:700;width:100%;box-shadow:0 4px 15px rgba(0,0,0,0.2)}.start-button:hover{transform:translateY(-3px);box-shadow:0 6px 20px rgba(0,0,0,0.3)}@keyframes pop-in{0%{transform:scale(.5);opacity:0}100%{transform:scale(1);opacity:1}}</style></head><body><div class=container><h1>ക്വിസ് തയ്യാറാണ്!</h1><p><b>{{ filename }}</b><br>ആകെ <span class=total-q>{{ total_questions }}</span> ചോദ്യങ്ങൾ ലഭ്യമാണ്.</p><p>നിങ്ങൾക്ക് പങ്കെടുക്കാൻ ആഗ്രഹിക്കുന്ന ചോദ്യങ്ങളുടെ എണ്ണം തിരഞ്ഞെടുക്കുക.</p><form action="{{ url_for('quiz') }}" method=post><div class=form-group><label for=start>തുടക്കം:</label><input type=number id=start name=start_q value=1 min=1 max={{ total_questions }}><label for=end>അവസാനം:</label><input type=number id=end name=end_q value={{ total_questions }} min=1 max={{ total_questions }}></div><button type=submit class=start-button>ക്വിസ് ആരംഭിക്കുക</button></form></div></body></html>
"""

QUIZ_PAGE_TEMPLATE = """
<!DOCTYPE html><html lang="ml"><head><meta charset="UTF-8"><title>{{ filename }} - ക്വിസ്</title><meta name="viewport" content="width=device-width, initial-scale=1.0"><style>@import url('https://fonts.googleapis.com/css2?family=Manjari:wght@400;700&family=Noto+Sans+Malayalam:wght@400;700&display=swap');body{font-family:'Noto Sans Malayalam','Manjari',sans-serif;background-color:#f4f7f6;display:flex;justify-content:center;align-items:center;min-height:100vh;padding:20px;color:#333}.quiz-container{background:#fff;padding:40px;border-radius:20px;box-shadow:0 10px 40px rgba(0,0,0,0.1);width:95%;max-width:850px;animation:fade-in .5s}.progress-container{display:flex;align-items:center;gap:15px;margin-bottom:25px}.progress-bar{flex-grow:1;height:12px;background-color:#e0e0e0;border-radius:6px;overflow:hidden}.progress{width:0;height:100%;background:linear-gradient(90deg,#43cea2,#185a9d);transition:width .4s ease-in-out}.progress-text{font-weight:700;color:#34495e}.question-header{font-size:1.3em;font-weight:700;color:#2c3e50;margin-bottom:20px;border-left:5px solid #43cea2;padding-left:15px}.question-text{font-size:1.2em;margin-bottom:30px;line-height:1.7}.options-container{display:grid;grid-template-columns:1fr;gap:15px}@media (min-width:768px){.options-container{grid-template-columns:1fr 1fr}}.option{background-color:#f8f9fa;border:2px solid #dfe6e9;border-radius:12px;padding:18px;cursor:pointer;transition:all .3s ease;text-align:left;display:flex;align-items:center;font-size:1.05em}.option:hover:not(.disabled){background-color:#e9ecef;border-color:#3498db;transform:translateY(-2px)}.option.disabled{cursor:default}.option.correct{background-color:#d1fae5;border-color:#10b981;color:#065f46;font-weight:700}.option.incorrect{background-color:#fee2e2;border-color:#ef4444;color:#991b1b;font-weight:700}.option-key{font-weight:700;margin-right:15px;background-color:#3498db;color:#fff;border-radius:50%;width:35px;height:35px;display:inline-flex;justify-content:center;align-items:center;flex-shrink:0;transition:transform .2s}.option:hover:not(.disabled) .option-key{transform:scale(1.1)}.option.correct .option-key{background-color:#10b981}.option.incorrect .option-key{background-color:#ef4444}.feedback{margin-top:25px;padding:18px;border-radius:12px;font-weight:700;text-align:center}.nav-button{display:none;margin-top:30px;background:linear-gradient(45deg,#3498db,#2980b9);color:#fff;border:none;padding:15px 30px;border-radius:10px;font-size:1.1em;cursor:pointer;transition:all .3s ease;float:right;box-shadow:0 4px 15px rgba(0,0,0,0.15)}.nav-button:hover{transform:translateY(-2px);box-shadow:0 6px 20px rgba(0,0,0,0.2)}.score-container{text-align:center;animation:pop-in .5s}.score-container h2{color:#2c3e50;font-size:2.8em}.score-container p{font-size:1.8em;margin:20px 0}.score-container a{display:inline-block;margin-top:25px;padding:15px 30px;background:linear-gradient(45deg,#185a9d,#43cea2);color:#fff;text-decoration:none;border-radius:10px;font-size:1.1em;transition:all .3s ease}.score-container a:hover{transform:translateY(-2px);box-shadow:0 6px 20px rgba(0,0,0,0.2)}@keyframes fade-in{from{opacity:0;transform:scale(.95)}to{opacity:1;transform:scale(1)}}@keyframes pop-in{0%{transform:scale(.5);opacity:0}100%{transform:scale(1);opacity:1}}</style></head><body><div class=quiz-container><div id=quiz-area><div class=progress-container><div class=progress-bar><div class=progress id=progress-bar-fill></div></div><div class=progress-text id=progress-text></div></div><div id=question-header></div><div id=question-text></div><div id=options-container class=options-container></div><div id=feedback class=feedback style=display:none></div><button id=next-button class=nav-button>അടുത്ത ചോദ്യം</button></div><div id=score-container style=display:none><h2>ക്വിസ് പൂർത്തിയായി!</h2><p id=score-text></p><a href="/">പുതിയ ക്വിസ് തുടങ്ങുക</a></div></div><script>const questionNumbers=Array.from({length:{{ end_q-start_q+1 }}},((_,t)=>t+{{ start_q }}));let currentQuestionIndex=0,score=0,answerChecked=!1;async function loadQuestion(){if(currentQuestionIndex>=questionNumbers.length)return void showScore();const t=currentQuestionIndex+1,e=questionNumbers.length;document.getElementById("progress-bar-fill").style.width=t/e*100+"%",document.getElementById("progress-text").textContent=`${t} / ${e}`;const n=questionNumbers[currentQuestionIndex],o=await fetch(`/get_question/${n}`),s=await o.json();document.getElementById("question-header").textContent=`ചോദ്യം ${t}`,document.getElementById("question-text").textContent=s.question;const a=document.getElementById("options-container");a.innerHTML="",document.getElementById("feedback").style.display="none",document.getElementById("next-button").style.display="none",answerChecked=!1,Object.entries(s.options).forEach((([t,e])=>{const n=document.createElement("div");n.classList.add("option"),n.dataset.key=t,n.innerHTML=`<span class=option-key>${t}</span><span>${e}</span>`,n.addEventListener("click",(()=>checkAnswer(t,s.correct_answer))),a.appendChild(n)}))}function checkAnswer(t,e){if(answerChecked)return;answerChecked=!0;const n=document.getElementById("feedback"),o=document.querySelectorAll(".option");o.forEach((n=>{n.classList.add("disabled"),n.dataset.key===e?n.classList.add("correct"):n.dataset.key===t&&n.classList.add("incorrect")})),t===e?(score+=1,n.textContent="ശരിയുത്തരം! (+1 മാർക്ക്)",n.className="feedback correct"):(score-=.25,n.innerHTML=`തെറ്റായ ഉത്തരം. (-0.25 മാർക്ക്).<br>ശരിയുത്തരം: <strong>${e}) ${document.querySelector(`.option[data-key='${e}']`).innerText.slice(1).trim()}</strong>`,n.className="feedback incorrect"),n.style.display="block",document.getElementById("next-button").style.display="block"}function showScore(){document.getElementById("quiz-area").style.display="none";const t=document.getElementById("score-container"),e=questionNumbers.length;document.getElementById("score-text").textContent=`നിങ്ങളുടെ സ്കോർ: ${score.toFixed(2)} / ${e}`,t.style.display="block"}document.getElementById("next-button").addEventListener("click",(()=>{currentQuestionIndex++,loadQuestion()})),document.addEventListener("DOMContentLoaded",loadQuestion);</script></body></html>
"""


# --- Flask Application Logic ---
@app.route('/', methods=['GET'])
def home():
    session.clear()
    return render_template_string(UPLOAD_TEMPLATE)

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'pdf_file' not in request.files:
        flash('ഫയൽ തിരഞ്ഞെടുത്തിട്ടില്ല')
        return redirect(url_for('home'))
    
    file = request.files['pdf_file']
    if file.filename == '' or not allowed_file(file.filename):
        flash('അനുവദനീയമല്ലാത്ത ഫയൽ. PDF ഫയൽ മാത്രം അപ്‌ലോഡ് ചെയ്യുക.')
        return redirect(url_for('home'))

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    questions = parse_questions_from_pdf(filepath)
    os.remove(filepath)
    
    if not questions:
        flash('PDF-ൽ നിന്ന് ചോദ്യങ്ങൾ കണ്ടെത്താനായില്ല. ഫയലിന്റെ ഘടന പരിശോധിക്കുക.')
        return redirect(url_for('home'))

    quiz_id = str(uuid.uuid4())
    QUIZ_SESSIONS[quiz_id] = {'questions': questions, 'filename': filename}
    session['quiz_id'] = quiz_id
    
    return redirect(url_for('select_range'))

@app.route('/select_range')
def select_range():
    quiz_id = session.get('quiz_id')
    if not quiz_id or quiz_id not in QUIZ_SESSIONS:
        flash('ക്വിസ് സെഷൻ കണ്ടെത്തിയില്ല. ദയവായി വീണ്ടും ഫയൽ അപ്‌ലോഡ് ചെയ്യുക.')
        return redirect(url_for('home'))
    
    quiz_data = QUIZ_SESSIONS[quiz_id]
    return render_template_string(
        SELECT_RANGE_TEMPLATE, 
        total_questions=len(quiz_data['questions']),
        filename=quiz_data['filename']
    )

@app.route('/quiz', methods=['POST'])
def quiz():
    quiz_id = session.get('quiz_id')
    if not quiz_id or quiz_id not in QUIZ_SESSIONS:
        return redirect(url_for('home'))
    
    quiz_data = QUIZ_SESSIONS[quiz_id]
    questions = quiz_data['questions']
    try:
        start_q_index = int(request.form.get('start_q', 1)) - 1
        end_q_index = int(request.form.get('end_q', len(questions))) - 1
    except (ValueError, TypeError):
        start_q_index = 0
        end_q_index = len(questions) - 1
    
    if start_q_index < 0: start_q_index = 0
    if end_q_index >= len(questions): end_q_index = len(questions) - 1
    if start_q_index > end_q_index: start_q_index = end_q_index

    start_q_num = questions[start_q_index]['number']
    end_q_num = questions[end_q_index]['number']

    return render_template_string(
        QUIZ_PAGE_TEMPLATE, 
        start_q=start_q_num, 
        end_q=end_q_num,
        filename=quiz_data['filename']
    )

@app.route('/get_question/<int:q_num>')
def get_question(q_num):
    quiz_id = session.get('quiz_id')
    if not quiz_id or quiz_id not in QUIZ_SESSIONS:
        return jsonify({"error": "Quiz session not found"}), 404
        
    questions = QUIZ_SESSIONS[quiz_id]['questions']
    question = next((q for q in questions if q['number'] == q_num), None)
    
    if question:
        return jsonify(question)
    return jsonify({"error": "Question not found"}), 404

# --- Main Execution ---
if __name__ == '__main__':
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    print("\nStarting the professional quiz application...")
    print("Open http://127.0.0.1:5000 in your browser.")
    app.run(debug=True)
