import os
from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory, jsonify
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import secrets


# Configurations
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf', 'docx', 'txt', 'jpg', 'png'}

# Initialize app
app = Flask(__name__)
app.secret_key = secrets.token_hex(16)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///printables.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Initialize database
db = SQLAlchemy(app)

# User Model
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)

# Log Model (optional)
class Log(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    action = db.Column(db.String(100), nullable=False)
    filename = db.Column(db.String(300))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html', now=datetime.utcnow)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = generate_password_hash(request.form['password'])
        if User.query.filter_by(username=username).first():
            return 'Username already exists'
        new_user = User(username=username, password=password)
        db.session.add(new_user)
        db.session.commit()
        os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], username), exist_ok=True)
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and check_password_hash(user.password, request.form['password']):
            session['user_id'] = user.id
            session['username'] = user.username
            return redirect(url_for('dashboard'))
        return 'Invalid credentials'
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user_folder = os.path.join(app.config['UPLOAD_FOLDER'], session['username'])
    files = os.listdir(user_folder) if os.path.exists(user_folder) else []
    return render_template('dashboard.html', files=files)

@app.route('/upload', methods=['POST'])
def upload():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    files = request.files.getlist('files')
    upload_path = os.path.join(app.config['UPLOAD_FOLDER'], session['username'])
    os.makedirs(upload_path, exist_ok=True)
    for file in files:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(upload_path, filename))
            db.session.add(Log(user_id=session['user_id'], action='upload', filename=filename))
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/files/<filename>')
def serve_file(filename):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return send_from_directory(os.path.join(app.config['UPLOAD_FOLDER'], session['username']), filename)

@app.route('/delete/<filename>', methods=['POST'])
def delete_file(filename):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], session['username'], filename)
    if os.path.exists(file_path):
        os.remove(file_path)
        db.session.add(Log(user_id=session['user_id'], action='delete', filename=filename))
        db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/print/<filename>', methods=['POST'])
def print_file(filename):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], session['username'], filename)
    if os.path.exists(file_path):
        os.remove(file_path)
        db.session.add(Log(user_id=session['user_id'], action='print', filename=filename))
        db.session.commit()
    return '', 204

# Run setup if needed
if __name__ == '__main__':
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    with app.app_context(): 
        db.create_all()
    app.run(debug=True)
