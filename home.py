# Importing necessary libraries for Flask, SQLAlchemy, data manipulation, encryption, and file system operations
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
import pandas as pd
import numpy as np
import os
import bcrypt

# Initialize Flask application
app = Flask(__name__)
# Configuration for SQLAlchemy database URI pointing to a SQLite database
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
# Disabling the modification tracking feature of SQLAlchemy to improve performance
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# Secret key for securely signing the session cookie. This should be securely managed in production.
app.config['SECRET_KEY'] = 'secret'
# Directory to save uploaded datasets and allowed file types
app.config['UPLOAD_FOLDER'] = 'datasets'
app.config['ALLOWED_EXTENSIONS'] = {'csv'}

# Initialize SQLAlchemy with Flask app settings
db = SQLAlchemy(app)

# Route for the home page, which renders an HTML template
@app.route("/", methods=['GET'])
def home():
    return render_template('index.html')

# Function to check allowed file types
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# Route for uploading and converting datasets
@app.route('/upload', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        # Check if the post request has the file part
        if 'file' not in request.files:
            return redirect(request.url)
        file = request.files['file']
        # If user does not select file, browser also submits an empty part without filename
        if file.filename == '':
            return redirect(request.url)
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            return redirect(url_for('convert_grades', filename=filename))
    return render_template('upload.html')

# Route to convert uploaded dataset
@app.route('/convert_grades/<filename>')
def convert_grades(filename):
    try:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        df = pd.read_csv(file_path)
        df = df.fillna(0)
        df = df.iloc[1:]
        quiz_columns = [col for col in df.columns if 'Quiz' in col and 'LOA' not in col and 'weight' in col]

        for quiz_col in quiz_columns:
            split = quiz_col.split(" ")
            loa_quiz_col = [col for col in df.columns if (f'LOA-{split[0]}{str(split[1])} ' in col or f'LOA-{split[0]} {str(split[1])} ' in col)]
            if loa_quiz_col:
                loa_quiz_col = loa_quiz_col[0]
                df[loa_quiz_col] = df[loa_quiz_col].replace('N/A', 0).fillna(0).astype(float)
                df[quiz_col] = df[quiz_col].astype(float) + df[loa_quiz_col].astype(float)
                df[quiz_col].loc[1] /= 2.0

        # Step 1: Filter required columns
        keywords = ['standard', 'medium', 'heavy']
        # Keep columns that contain any of the keywords or are 'Student' or 'SIS Login ID', ignoring case
        columns_to_keep = [col for col in df.columns if any(keyword.lower() in col.lower() for keyword in keywords) 
                        or col in ['Student', 'SIS Login ID']]
        df_filtered = df[columns_to_keep]


        # Step 2: Convert grades to decimals
        # Find the row with 'Points Possible' (assuming it's the second row)
        points_possible = df_filtered.iloc[0]

        # Convert grades, treating 'N/A' as 0
        for col in df_filtered.columns[2:]:  # Skip 'Student' and 'SIS Login ID' columns
            # Convert all 'N/A' to 0, coerce any errors, fill NaN with 0, and convert to float
            df_filtered[col] = pd.to_numeric(df_filtered[col].replace('N/A', 0), errors='coerce').fillna(0).astype(float)
            
            # Safely divide the values in the DataFrame using .loc to avoid the SettingWithCopyWarning
            df_filtered.loc[:, col] = df_filtered[col] / float(points_possible[col])

        df_filtered = df_filtered.loc[:, ~df_filtered.columns.str.contains('LOA')]

        # Remove the 'Points Possible' row to leave only student data
        df_final = df_filtered.drop(1).reset_index(drop=True)

        output_file_path = os.path.join(app.config['UPLOAD_FOLDER'], 'allgrades.csv')
        df_final.to_csv(output_file_path, index=False)
    except Exception as e:
        return jsonify({"message": f"There was an error :  {e}"})
    return jsonify({"message": f"Dataset converted and saved to {output_file_path}"})

# Route for the flexigrade page, which checks if the user is a professor before proceeding
@app.route('/flexigrade')
def flexigrade():
    if session.get('professor'):
        return render_template('flexinetid.html')
    else:
        return render_template('notloggedin.html')

# A route to display the flexicheck page, typically a form or informational page
@app.route('/flexicheck', methods=['GET', 'POST'])
def flexicheck():
    return render_template('flexicheck.html')

# Route for professors to view grades based on student netid
@app.route('/profview', methods=['POST'])
def loaddemogrades():
    netid = request.form['netid']
    if os.path.isfile(os.path.join(os.getcwd() + '/datasets/allgrades.csv')):
        gradesDF = pd.read_csv(os.path.join(os.getcwd() + '/datasets/allgrades.csv'))

    grade_netid = gradesDF[gradesDF['SIS Login ID'] == netid]
    
    # Filtering columns related to quizzes, heavy assignments, and other types
    grade_netid_quiz = [col for col in grade_netid.columns if 'quiz' in col.lower()]
    grade_netid_heavy = [col for col in grade_netid.columns if 'heavy' in col.lower()]
    grade_netid_medium = [col for col in grade_netid.columns if ('quiz' not in col.lower() and 'heavy' not in col.lower())][2:]

    # Converting the filtered data to JSON format for use in the frontend
    filtered_json = grade_netid.to_json(orient='records')
    return render_template('flexigrade.html', grades=filtered_json, quizzes=grade_netid_quiz, medium=grade_netid_medium, heavy=grade_netid_heavy)

# Route for loading grades of logged in student
@app.route('/loadgrades', methods=['GET'])
def loadgrades():
    netid = session.get('netid')
    if netid:
        if os.path.isfile(os.path.join(os.getcwd() + '/datasets/allgrades.csv')):
            gradesDF = pd.read_csv(os.path.join(os.getcwd() + '/datasets/allgrades.csv'))
        grade_netid = gradesDF[gradesDF['SIS Login ID'] == netid]

        grade_netid_quiz = [col for col in grade_netid.columns if 'quiz' in col.lower()]
        grade_netid_heavy = [col for col in grade_netid.columns if 'heavy' in col.lower()]
        grade_netid_medium = [col for col in grade_netid.columns if ('quiz' not in col.lower() and 'heavy' not in col.lower())][2:]       
        
        filtered_json = grade_netid.to_json(orient='records')
        return render_template('flexigrade.html', grades=filtered_json, quizzes=grade_netid_quiz, medium=grade_netid_medium, heavy=grade_netid_heavy)
    else:
        return render_template('notloggedin.html')

# SQLAlchemy User model for storing user credentials
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)

# To use security question as fields in the DB table.
# class User(db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     username = db.Column(db.String(80), unique=True, nullable=False)
#     password = db.Column(db.String(120), nullable=False)
#     security_question = db.Column(db.String(255), nullable=True)
#     security_answer = db.Column(db.String(255), nullable=True)


# Routes for reset password.
# @app.route('/forgot-password', methods=['GET', 'POST'])
# def forgot_password():
#     if request.method == 'POST':
#         username = request.form['username']
#         user = User.query.filter_by(username=username).first()
#         if user:
#             return render_template('reset_password.html', question=user.security_question)
#         else:
#             return 'User not found', 404
#     return render_template('forgot_password.html')

# @app.route('/reset-password', methods=['POST'])
# def reset_password():
#     username = request.form['username']  # Ensure this is passed from the form or via the session
#     answer = request.form['answer']
#     new_password = request.form['new_password']
#     user = User.query.filter_by(username=username).first()
#     if user and user.security_answer == answer:
#         hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
#         user.password = hashed_password
#         db.session.commit()
#         return 'Password has been reset successfully'
#     return 'Invalid answer or user not found', 401


# Route for deleting a user, with error handling
@app.route('/delete_user/<username>', methods=['GET'])
def delete_user(username):
    user = User.query.filter_by(username=username).first()
    if user:
        try:
            db.session.delete(user)
            db.session.commit()
            session.clear()
            return jsonify({"message": f"User {username} deleted successfully"}), 200
        except Exception as e:
            db.session.rollback()
            return jsonify({"error": "An error occurred while deleting the user", "details": str(e)}), 500
    else:
        return jsonify({"error": "User not found"}), 404

# Registration route to create new users, with error handling
@app.route('/register', methods=['POST', 'GET'])
def register():
    if request.method == "POST":
        username = request.json['username']
        # Password hashing for security using bcrypt
        password = bcrypt.hashpw(request.json['password'].encode('utf-8'), bcrypt.gensalt())
        new_user = User(username=username, password=password)
        
        db.session.add(new_user)
        try:
            db.session.commit()
            return jsonify({"message": "User registered successfully"}), 201
        except Exception as e:
            db.session.rollback()
            return jsonify({"message": "An error occurred."+'\n'+"A user with this username already exists."+'\nOR - '+str(e.args)}), 500
    if request.method == "GET":
        return render_template('register.html')

# Route for user logout, clears the session
@app.route('/logout')
def logout():
    session.clear()
    return jsonify({"message": "Logged out successfully", "redirect": "/login"}), 200

# Login route for user authentication
@app.route('/login', methods=['POST', 'GET'])
def login():
    if request.method == "GET":
        return render_template('login.html')
    
    if request.method == "POST":
        username = request.json['username']
        password = request.json['password'].encode('utf-8')
        
        user = User.query.filter_by(username=username).first()
        # Special login condition for professor, setting session differently
        if username == "timielinski":
            if user and bcrypt.checkpw(password, user.password):
                session['professor'] = True
                return jsonify({"message": "Professor login successful", "redirect": "/flexigrade"}), 200
            elif user:
                return jsonify({"error": "Incorrect password"}), 401
            else:
                return jsonify({"error": "User not found"}), 404
        else:
            if user and bcrypt.checkpw(password, user.password):
                session['netid'] = username
                return jsonify({"message": "Login successful", "redirect": "/loadgrades"}), 200
            elif user:
                return jsonify({"error": "Incorrect password"}), 401
            else:
                return jsonify({"error": "User not found"}), 404

# Demo route, usually for demonstrating a feature or concept
@app.route('/flexidemo')
def flexidemo():
    return render_template('flexinetid-demo.html')

# Main entry point for the application, with debug enabled and listening on all network interfaces
if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Create all database tables
    app.run(debug=True, host='0.0.0.0')
