from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import boto3
from botocore.exceptions import ClientError
import hashlib
import uuid
from datetime import datetime, timedelta
import os
from functools import wraps

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-in-production'

# AWS Configuration
AWS_REGION = 'us-east-1'
AWS_ACCESS_KEY_ID = 'your-access-key-id'
AWS_SECRET_ACCESS_KEY = 'your-secret-access-key'

# Initialize AWS services
try:
    dynamodb = boto3.resource(
        'dynamodb',
        region_name=AWS_REGION,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY
    )
    
    sns = boto3.client(
        'sns',
        region_name=AWS_REGION,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY
    )
    
    # DynamoDB Tables
    users_table = dynamodb.Table('users')
    appointments_table = dynamodb.Table('appointments')
    
except Exception as e:
    print(f"AWS Configuration Error: {e}")
    # For local development, you can use local DynamoDB or mock data
    dynamodb = None
    sns = None

def hash_password(password):
    """Hash password for secure storage"""
    return hashlib.sha256(password.encode()).hexdigest()

def login_required(f):
    """Decorator to require login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def doctor_required(f):
    """Decorator to require doctor role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_type' not in session or session['user_type'] != 'doctor':
            flash('Access denied. Doctor login required.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def send_sms_notification(phone_number, message):
    """Send SMS notification using AWS SNS"""
    try:
        if sns:
            response = sns.publish(
                PhoneNumber=phone_number,
                Message=message
            )
            return response
    except Exception as e:
        print(f"SMS sending error: {e}")
        return None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user_type = request.form['user_type']
        
        hashed_password = hash_password(password)
        
        try:
            if users_table:
                response = users_table.get_item(
                    Key={'email': email}
                )
                
                if 'Item' in response:
                    user = response['Item']
                    if user['password'] == hashed_password and user['user_type'] == user_type:
                        session['user_id'] = user['user_id']
                        session['user_type'] = user['user_type']
                        session['name'] = user['name']
                        session['email'] = user['email']
                        
                        if user_type == 'doctor':
                            return redirect(url_for('doctor_dashboard'))
                        else:
                            return redirect(url_for('patient_dashboard'))
                    else:
                        flash('Invalid credentials', 'error')
                else:
                    flash('User not found', 'error')
            else:
                # Mock login for development
                if email == 'dr.sharma@hospital.com' and password == 'doctor123' and user_type == 'doctor':
                    session['user_id'] = 'doc1'
                    session['user_type'] = 'doctor'
                    session['name'] = 'Dr. Rajesh Sharma'
                    session['email'] = email
                    return redirect(url_for('doctor_dashboard'))
                elif email == 'priya.patient@email.com' and password == 'patient123' and user_type == 'patient':
                    session['user_id'] = 'pat1'
                    session['user_type'] = 'patient'
                    session['name'] = 'Priya Patel'
                    session['email'] = email
                    return redirect(url_for('patient_dashboard'))
                else:
                    flash('Invalid credentials', 'error')
                    
        except Exception as e:
            flash('Login error occurred', 'error')
            print(f"Login error: {e}")
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        user_data = {
            'user_id': str(uuid.uuid4()),
            'name': request.form['name'],
            'email': request.form['email'],
            'phone': request.form['phone'],
            'password': hash_password(request.form['password']),
            'user_type': request.form['user_type'],
            'created_at': datetime.now().isoformat()
        }
        
        if request.form['user_type'] == 'doctor':
            user_data['specialization'] = request.form['specialization']
            user_data['license_number'] = request.form['license_number']
        
        try:
            if users_table:
                users_table.put_item(Item=user_data)
                flash('Registration successful! Please login.', 'success')
                return redirect(url_for('login'))
            else:
                flash('Registration successful! Please login with demo credentials.', 'success')
                return redirect(url_for('login'))
        except Exception as e:
            flash('Registration failed', 'error')
            print(f"Registration error: {e}")
    
    return render_template('register.html')

@app.route('/patient/dashboard')
@login_required
def patient_dashboard():
    if session['user_type'] != 'patient':
        return redirect(url_for('login'))
    
    # Get upcoming appointments
    upcoming_appointments = []
    past_appointments = []
    
    try:
        if appointments_table:
            response = appointments_table.scan(
                FilterExpression='patient_id = :patient_id',
                ExpressionAttributeValues={':patient_id': session['user_id']}
            )
            appointments = response['Items']
            
            current_time = datetime.now()
            for apt in appointments:
                apt_datetime = datetime.fromisoformat(apt['appointment_datetime'])
                if apt_datetime > current_time:
                    upcoming_appointments.append(apt)
                else:
                    past_appointments.append(apt)
        else:
            # Mock data for development
            upcoming_appointments = [
                {
                    'appointment_id': '1',
                    'doctor_name': 'Dr. Rajesh Sharma',
                    'specialization': 'Cardiology',
                    'appointment_datetime': (datetime.now() + timedelta(days=2)).isoformat(),
                    'status': 'scheduled'
                }
            ]
            past_appointments = [
                {
                    'appointment_id': '2',
                    'doctor_name': 'Dr. Anjali Verma',
                    'specialization': 'General Medicine',
                    'appointment_datetime': (datetime.now() - timedelta(days=30)).isoformat(),
                    'status': 'completed'
                }
            ]
    except Exception as e:
        print(f"Error fetching appointments: {e}")
    
    return render_template('patient_dashboard.html', 
                         upcoming_appointments=upcoming_appointments,
                         past_appointments=past_appointments)

@app.route('/doctor/dashboard')
@login_required
@doctor_required
def doctor_dashboard():
    # Get today's appointments
    today_appointments = []
    upcoming_appointments = []
    
    try:
        if appointments_table:
            response = appointments_table.scan(
                FilterExpression='doctor_id = :doctor_id',
                ExpressionAttributeValues={':doctor_id': session['user_id']}
            )
            appointments = response['Items']
            
            today = datetime.now().date()
            for apt in appointments:
                apt_date = datetime.fromisoformat(apt['appointment_datetime']).date()
                if apt_date == today:
                    today_appointments.append(apt)
                elif apt_date > today:
                    upcoming_appointments.append(apt)
        else:
            # Mock data for development
            today_appointments = [
                {
                    'appointment_id': '1',
                    'patient_name': 'Priya Patel',
                    'appointment_datetime': datetime.now().replace(hour=14, minute=30).isoformat(),
                    'status': 'scheduled'
                }
            ]
            upcoming_appointments = [
                {
                    'appointment_id': '2',
                    'patient_name': 'Amit Kumar',
                    'appointment_datetime': (datetime.now() + timedelta(days=1)).replace(hour=10, minute=0).isoformat(),
                    'status': 'scheduled'
                }
            ]
    except Exception as e:
        print(f"Error fetching appointments: {e}")
    
    return render_template('doctor_dashboard.html',
                         today_appointments=today_appointments,
                         upcoming_appointments=upcoming_appointments)

@app.route('/book-appointment', methods=['GET', 'POST'])
@login_required
def book_appointment():
    if session['user_type'] != 'patient':
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        appointment_data = {
            'appointment_id': str(uuid.uuid4()),
            'patient_id': session['user_id'],
            'patient_name': session['name'],
            'doctor_id': request.form['doctor_id'],
            'doctor_name': request.form['doctor_name'],
            'appointment_datetime': request.form['appointment_datetime'],
            'reason': request.form['reason'],
            'status': 'scheduled',
            'created_at': datetime.now().isoformat()
        }
        
        try:
            if appointments_table:
                appointments_table.put_item(Item=appointment_data)
                
                # Send SMS notification
                message = f"Appointment booked with {appointment_data['doctor_name']} on {appointment_data['appointment_datetime']}"
                # send_sms_notification('+91xxxxxxxxxx', message)  # Replace with actual phone
                
                flash('Appointment booked successfully!', 'success')
            else:
                flash('Appointment booked successfully! (Demo mode)', 'success')
            return redirect(url_for('patient_dashboard'))
        except Exception as e:
            flash('Failed to book appointment', 'error')
            print(f"Booking error: {e}")
    
    # Get available doctors
    doctors = []
    try:
        if users_table:
            response = users_table.scan(
                FilterExpression='user_type = :user_type',
                ExpressionAttributeValues={':user_type': 'doctor'}
            )
            doctors = response['Items']
        else:
            # Mock doctors for development
            doctors = [
                {
                    'user_id': 'doc1',
                    'name': 'Dr. Rajesh Sharma',
                    'specialization': 'Cardiology'
                },
                {
                    'user_id': 'doc2',
                    'name': 'Dr. Anjali Verma',
                    'specialization': 'General Medicine'
                },
                {
                    'user_id': 'doc3',
                    'name': 'Dr. Suresh Gupta',
                    'specialization': 'Pediatrics'
                }
            ]
    except Exception as e:
        print(f"Error fetching doctors: {e}")
    
    return render_template('book_appointment.html', doctors=doctors)

@app.route('/appointment-history')
@login_required
def appointment_history():
    appointments = []
    
    try:
        if appointments_table:
            if session['user_type'] == 'patient':
                response = appointments_table.scan(
                    FilterExpression='patient_id = :patient_id',
                    ExpressionAttributeValues={':patient_id': session['user_id']}
                )
            else:
                response = appointments_table.scan(
                    FilterExpression='doctor_id = :doctor_id',
                    ExpressionAttributeValues={':doctor_id': session['user_id']}
                )
            appointments = response['Items']
        else:
            # Mock data for development
            if session['user_type'] == 'patient':
                appointments = [
                    {
                        'appointment_id': '1',
                        'doctor_name': 'Dr. Rajesh Sharma',
                        'specialization': 'Cardiology',
                        'appointment_datetime': '2024-01-15T10:00:00',
                        'status': 'completed',
                        'reason': 'Regular checkup'
                    },
                    {
                        'appointment_id': '2',
                        'doctor_name': 'Dr. Anjali Verma',
                        'specialization': 'General Medicine',
                        'appointment_datetime': '2024-02-20T14:30:00',
                        'status': 'completed',
                        'reason': 'Fever and headache'
                    }
                ]
            else:
                appointments = [
                    {
                        'appointment_id': '1',
                        'patient_name': 'Priya Patel',
                        'appointment_datetime': '2024-01-15T10:00:00',
                        'status': 'completed',
                        'reason': 'Regular checkup'
                    },
                    {
                        'appointment_id': '2',
                        'patient_name': 'Amit Kumar',
                        'appointment_datetime': '2024-02-20T14:30:00',
                        'status': 'completed',
                        'reason': 'Follow-up consultation'
                    }
                ]
    except Exception as e:
        print(f"Error fetching appointment history: {e}")
    
    return render_template('appointment_history.html', appointments=appointments)

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully', 'success')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)