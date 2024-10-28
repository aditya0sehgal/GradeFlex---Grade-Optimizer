# Importing necessary libraries for Flask, SQLAlchemy, data manipulation, encryption, and file system operations
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
import pandas as pd
import numpy as np
import os
import bcrypt
import requests
from dotenv import dotenv_values

# Initialize Flask application
app = Flask(__name__)
env_values = dotenv_values(".env")
# Configuration for SQLAlchemy database URI pointing to a SQLite database
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
# Disabling the modification tracking feature of SQLAlchemy to improve performance
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# Secret key for securely signing the session cookie. This should be securely managed in production.
app.config['SECRET_KEY'] = env_values["SECRET_KEY"]
# Directory to save uploaded datasets and allowed file types
app.config['UPLOAD_FOLDER'] = 'datasets'
app.config['ALLOWED_EXTENSIONS'] = {'csv'}

# Initialize SQLAlchemy with Flask app settings
db = SQLAlchemy(app)
course_weight_mapping_dict = {}
access_token = env_values["CANVAS_ACCESS_TOKEN"]
canvas_url = env_values["CANVAS_URL"]
COURSE_ID = env_values["DATA_101_COURSEID"]

# Route for the home page, which renders an HTML template
@app.route("/", methods=['GET'])
def home():
    return render_template('index.html')

# Function to check allowed file types
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# Function to fetch and process weight mappings
def get_weight_mappings():
    sheet_id = '1iIr0y8uHw7GK_SpT1IcgfrXf8kO0FKGzgDla4mEiI1k'
    sheet_name = 'WeightMappings'
    url = f'https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={sheet_name}'

    weight_mappings = pd.read_csv(url)
    weight_mappings.fillna('', inplace=True)
    weight_mappings = weight_mappings.iloc[:, :4]

    # Initialize an empty dictionary
    course_section_dict = {}

    # Group the DataFrame by 'Full Course Code' and 'Section'
    grouped = weight_mappings.groupby(['Full Course Code', 'Section'])

    # Iterate through each group
    for (course, section), group in grouped:
        weight_dict = dict(zip(group['Type'], group['Weight Multiplier']))
        course_section_dict[course + " - " + str(section)] = weight_dict

    return course_section_dict

# Function to fetch student data from Canvas
def fetch_canvas_data(netid):
    headers = {
        "Authorization": "Bearer " + access_token
    }

    # Fetch student netid and name mapping
    # print(canvas_url + "/api/v1/courses/"+COURSE_ID+"/students")
    response = requests.get(canvas_url + "/api/v1/courses/"+COURSE_ID+"/students", headers=headers)
    student_netid_id_and_name_mapping = {}

    if response.status_code == 200:
        result = response.json()
        
        for student in result:
            if student.get('sis_user_id'):
                student_netid_id_and_name_mapping[student.get('sis_user_id')] = [student.get('id'), student.get('name')]
    else:
        raise Exception("Error fetching student data: " + str(response.status_code))
    # print(student_netid_id_and_name_mapping)
    student_id = student_netid_id_and_name_mapping.get(netid)[0]
    # print(student_id)
    # Fetch student grades
    response = requests.get(canvas_url + "/api/v1/courses/"+COURSE_ID+"/students/submissions?student_ids[]="+str(student_id)+"&grouped=true&include[]=assignment&per_page=20", headers=headers)
    all_student_grades = []

    if response.status_code == 200:
        current_students = response.json()
        
        for student in current_students:
            if student.get('sis_user_id'):
                all_student_grades.append(student)
        
        while response.links['current']['url'] != response.links['last']['url']:
            response = requests.get(response.links['next']['url'], headers=headers)
            current_students = response.json()
            for student in current_students:
                if student.get('sis_user_id'):
                    all_student_grades.append(student)
    else:
        raise Exception("Error fetching grades: " + str(response.status_code))
    # print(student_netid_id_and_name_mapping.get(netid)[1])
    return [all_student_grades, student_netid_id_and_name_mapping.get(netid)[1]]



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
    global course_weight_mapping_dict
    
    netid = request.form['netid']
    if os.path.isfile(os.path.join(os.getcwd() + '/datasets/allgrades.csv')):
        gradesDF = pd.read_csv(os.path.join(os.getcwd() + '/datasets/allgrades.csv'))

    if(netid not in gradesDF['SIS Login ID'].values):
        return render_template('nonetid.html', message = "NetID not found in the dataset for this class")
    grade_netid = gradesDF[gradesDF['SIS Login ID'] == netid]
    

    try:
        course_weight_mapping_dict = get_weight_mappings()
    except Exception as e:
        return jsonify({"message": f"There was an error: {e}"}), 500

    # Replace to generalize it to get the weight mapping for that particular course.
    # This could maybe be done in the get_weight_mappings function itself.
    # By passing the course code as an argument.
    weight_mapping = course_weight_mapping_dict['01:198:142 - 1']
    # print(weight_mapping)
    category_columns = {key: [] for key in weight_mapping.keys()}
    
    # Iterate over the columns and add them to the corresponding category
    for col in grade_netid.columns:
        for key in weight_mapping.keys():
            if key.lower() in col.lower():
                category_columns[key].append(col)
                break

    # Convert filtered data to JSON format for each category
    filtered_json = grade_netid.to_json(orient='records')
    # Create a nested dictionary structure for category_json
    category_json = {}
    for key, cols in category_columns.items():
        category_json[key] = grade_netid[cols].to_dict(orient='records')

    filtered_json = [grade_netid.to_json(orient='records')]
    return render_template('flexigrade.html', weight_mapping=weight_mapping, name=grade_netid['Student'].values[0], netid=grade_netid['SIS Login ID'].values[0], oldgrades=filtered_json, grades=category_json)

@app.route('/loadgrades', methods=['GET'])
def loadgrades():
    global course_weight_mapping_dict
    
    netid = session.get('netid')
    if not netid:
        return render_template('login.html', message="Please login to view grades")
    
    # Fetch and integrate Canvas data
    try:
        canvas_data, name = fetch_canvas_data(netid)
        canvas_grades = []
        for student in canvas_data:
            if student.get('sis_user_id') == netid:
                for assignment in student.get('submissions'):
                    if assignment.get('score') is not None and assignment.get('assignment').get('points_possible') != 0.0:
                        canvas_grades.append({
                            'assignment_name': assignment.get('assignment').get('name'),
                            'assignment_id': assignment.get('assignment_id'),
                            'score': assignment.get('score'),
                            'points_possible': assignment.get('assignment').get('points_possible'),
                            'percentage': f"{assignment.get('score') / assignment.get('assignment').get('points_possible'):.2f}"
                        })
    except Exception as e:
        return jsonify({"message": f"There was an error fetching Canvas data: {e}"}), 500
    # print(canvas_grades)

    # Assume course code and section are known or can be inferred
    course_code = '01:198:142'
    section = '1'

    try:
        course_weight_mapping_dict = get_weight_mappings()
        weight_mapping = course_weight_mapping_dict[f'{course_code} - {section}']
    except Exception as e:
        return jsonify({"message": f"There was an error: {e}"}), 500

    category_columns = {key: [] for key in weight_mapping.keys()}
    
    # Process Canvas grades to fit the structure
    for grade in canvas_grades:
        for key in weight_mapping.keys():
            if key.lower() in grade['assignment_name'].lower():
                category_columns[key].append(grade)
                break

    category_json = {}
    for key, grades in category_columns.items():
        category_json[key] = grades

    return render_template('flexigrade.html', weight_mapping=weight_mapping, name=name, netid=netid, grades=category_json)


# Route for loading grades of logged in student
@app.route('/loadgrades-test', methods=['GET'])
def loadgradestest():
    global course_weight_mapping_dict
    netid = "scd152"
    # Fetch and integrate Canvas data
    try:
        canvas_data, name = fetch_canvas_data(netid)
        canvas_grades = []
        for student in canvas_data:
            if student.get('sis_user_id') == netid:
                for assignment in student.get('submissions'):
                    if assignment.get('score') is not None and assignment.get('assignment').get('points_possible') != 0.0:
                        canvas_grades.append({
                            'assignment_name': assignment.get('assignment').get('name'),
                            'assignment_id': assignment.get('assignment_id'),
                            'score': assignment.get('score'),
                            'points_possible': assignment.get('assignment').get('points_possible'),
                            'percentage': f"{(assignment.get('score')/ assignment.get('assignment').get('points_possible') - 0.1):.2f}"
                        })
    except Exception as e:
        return jsonify({"message": f"There was an error fetching Canvas data: {e}"}), 500
    # print(canvas_grades)

    # Assume course code and section are known or can be inferred
    course_code = '01:198:142'
    section = '1'

    try:
        course_weight_mapping_dict = get_weight_mappings()
        weight_mapping = course_weight_mapping_dict[f'{course_code} - {section}']
    except Exception as e:
        return jsonify({"message": f"There was an error: {e}"}), 500

    category_columns = {key: [] for key in weight_mapping.keys()}
    
    # Process Canvas grades to fit the structure
    for grade in canvas_grades:
        for key in weight_mapping.keys():
            if key.lower() in grade['assignment_name'].lower():
                category_columns[key].append(grade)
                break

    category_json = {}
    for key, grades in category_columns.items():
        category_json[key] = grades

    return render_template('flexigrade.html', weight_mapping=weight_mapping, name="Demo User", netid="Demo NetID", grades=category_json)

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
                return jsonify({"message": "Login successful. Loading your grades...", "redirect": "/loadgrades"}), 200
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
