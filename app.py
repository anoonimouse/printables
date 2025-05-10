import os
from flask import Flask, flash, render_template, request, redirect, url_for, session, send_from_directory, jsonify
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import secrets
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer
import smtplib

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

#initialize mail
app.config['MAIL_SERVER'] = 'smtp.gmail.com'  # Or your provider
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'sharingboo@gmail.com'
app.config['MAIL_PASSWORD'] = 'hsgn cmdq xaeq hsgb'  # Use app password, not Gmail password
app.config['MAIL_DEFAULT_SENDER'] = 'sharingboo@gmail.com'

mail = Mail(app)
s = URLSafeTimedSerializer(app.secret_key)

# User Model
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    is_verified = db.Column(db.Boolean, default=False)
    email = db.Column(db.String(120), unique=True, nullable=False)

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
        email = request.form['email']  # Ensure this field exists in your form
        password = generate_password_hash(request.form['password'])

        # Check if username already exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'danger')
            return redirect(url_for('register'))

        # Check if email already exists
        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'danger')
            return redirect(url_for('register'))

        # Create user (default is_verified=False)
        new_user = User(username=username, email=email, password=password, is_verified=False)
        db.session.add(new_user)
        db.session.commit()

        # Create user upload folder
        os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], username), exist_ok=True)

        # Generate confirmation token and email
        token = s.dumps(username, salt='email-confirm')
        link = url_for('confirm_email', token=token, _external=True)

        msg = Message('Confirm Your Printables Account', recipients=[email])
        msg.body = f'Hello {username},\n\nClick this link to confirm your registration:\n{link}\n\nThis link expires in 1 hour.'
        mail.send(msg)

        flash('A confirmation email has been sent. Please check your inbox.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # Fetch user by username
        user = User.query.filter_by(username=request.form['username']).first()

        if user and check_password_hash(user.password, request.form['password']):
            # Check if the user has verified their email
            if not user.is_verified:
                flash('Please verify your email before logging in.')
                return redirect(url_for('login'))

            # If user is verified, proceed to login
            session['user_id'] = user.id
            session['username'] = user.username
            return redirect(url_for('dashboard'))

        flash('Invalid credentials', 'error')
    return render_template('login.html')


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

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.')
    return redirect(url_for('login'))

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

@app.route('/confirm/<token>')
def confirm_email(token):
    try:
        username = s.loads(token, salt='email-confirm', max_age=3600)  # 1 hour expiry
    except:
        flash('The confirmation link is invalid or has expired.', 'error')
        return redirect(url_for('login'))

    user = User.query.filter_by(username=username).first_or_404()
    if user.is_verified:
        flash('Account already verified. Please login.')
    else:
        user.is_verified = True
        db.session.commit()
        flash('Your account has been verified. You can now log in.')
    return redirect(url_for('login'))


# Run setup if needed
if __name__ == '__main__':
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    with app.app_context(): 
        db.create_all()
    app.run(debug=True)
