from flask import Flask, render_template, request, jsonify, session
from flask_sqlalchemy import SQLAlchemy
import pandas as pd
import numpy as np, os
import bcrypt

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'secret'  # Needed for session management. Set it manually on the server or read from a config file.
db = SQLAlchemy(app)
    
#
# Flex grade below
#

# Home landing page
@app.route("/" , methods=['GET'])
def home():
    return render_template('index.html')

@app.route('/flexigrade')
def flexigrade():
    if session.get('professor'):
        return render_template('flexinetid.html')
    else:
        return render_template('notloggedin.html')
    
@app.route('/flexicheck', methods=['GET', 'POST'])
def flexicheck():
    return render_template('flexicheck.html')
    
@app.route('/profview', methods=['POST'])
def loaddemogrades():
    netid = request.form['netid']

    if os.path.isfile(os.path.join(os.getcwd() +'/datasets/allgrades.csv')):
        gradesDF = pd.read_csv(os.path.join(os.getcwd() +'/datasets/allgrades.csv'))

    grade_netid = gradesDF[gradesDF['SIS Login ID'] == netid]
    
    grade_netid_quiz = [col for col in grade_netid.columns if 'quiz' in col.lower()]
    grade_netid_heavy = [col for col in grade_netid.columns if 'heavy' in col.lower()]
    grade_netid_medium = [col for col in grade_netid.columns if(('quiz' not in col.lower()) and ('heavy' not in col.lower()))][2:]

    filtered_json = grade_netid.to_json(orient='records')
    return render_template('flexigrade.html', grades = filtered_json, quizzes = grade_netid_quiz, medium = grade_netid_medium, heavy = grade_netid_heavy)

@app.route('/loadgrades', methods=['GET'])
def loadgrades():
    netid = session.get('netid')

    if netid:
        if os.path.isfile(os.path.join(os.getcwd() +'/datasets/allgrades.csv')):
            gradesDF = pd.read_csv(os.path.join(os.getcwd() +'/datasets/allgrades.csv'))

        grade_netid = gradesDF[gradesDF['SIS Login ID'] == netid]
        print(grade_netid)
        grade_netid_quiz = [col for col in grade_netid.columns if 'quiz' in col.lower()]
        grade_netid_heavy = [col for col in grade_netid.columns if 'heavy' in col.lower()]
        grade_netid_medium = [col for col in grade_netid.columns if(('quiz' not in col.lower()) and ('heavy' not in col.lower()))][2:]

        print(grade_netid_quiz)
        print(grade_netid_heavy)
        print(grade_netid_medium)
        
        filtered_json = grade_netid.to_json(orient='records')
        return render_template('flexigrade.html', grades = filtered_json, quizzes = grade_netid_quiz, medium = grade_netid_medium, heavy = grade_netid_heavy)
    
    else:
        return render_template('notloggedin.html')
   
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)

@app.route('/delete_user/<username>', methods=['GET'])
def delete_user(username):
    # Query the database for the user
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

@app.route('/register', methods=['POST', 'GET'])
def register():
    if request.method == "POST":
        username = request.json['username']
        password = bcrypt.hashpw(request.json['password'].encode('utf-8'), bcrypt.gensalt())
        new_user = User(username=username, password=password)
        
        db.session.add(new_user)
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(e)
            return jsonify({"message": "An error occurred."+'\n'+"A user with this username already exists."+'\nOR - '+str(e.args)}), 500

        return jsonify({"message": "User registered successfully"}), 201
 
    if request.method == "GET":
        return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()  # Clear the session
    return jsonify({"message": "Logged out successfully", "redirect": "/login"}), 200

@app.route('/login', methods=['POST', 'GET'])
def login():
    if request.method == "GET":
        return render_template('login.html')
    
    if request.method == "POST":
        username = request.json['username']
        password = request.json['password'].encode('utf-8')
        
        user = User.query.filter_by(username=username).first()
        if username == "timielinski" and bcrypt.checkpw(password, user.password):
            session['professor'] = True  # Save user ID in session
            return jsonify({"message": "Professor login successful", "redirect": "/flexigrade"}), 200

        else:
            if user and bcrypt.checkpw(password, user.password):
                session['netid'] = username  # Save user ID in session

                return jsonify({"message": "Login successful", "redirect": "/loadgrades"}), 200

            elif user:
                return jsonify({"error": "Incorrect password"}), 401
            else:
                return jsonify({"error": "User not found"}), 404
        
# Demo stuff below
@app.route('/flexidemo')
def flexidemo():
    return render_template('flexinetid-demo.html')
    
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0')