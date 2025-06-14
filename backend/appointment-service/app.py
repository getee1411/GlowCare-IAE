from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import os
import requests
from datetime import datetime
import jwt
from functools import wraps

app = Flask(__name__)
CORS(app)

# Database configuration
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'appointment.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your-secret-key'  # Change this in production

db = SQLAlchemy(app)

# Models
class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(100), nullable=False)
    treatment_id = db.Column(db.Integer, nullable=False)
    appointment_date = db.Column(db.Date, nullable=False)
    appointment_time = db.Column(db.String(5), nullable=False)  # Format: "HH:MM"
    status = db.Column(db.String(20), default='pending')  # pending, confirmed, completed, cancelled
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# Authentication decorator
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            token = request.headers['Authorization'].split(" ")[1]

        if not token:
            return jsonify({'message': 'Token is missing!'}), 401

        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            request.user_data = data
        except jwt.ExpiredSignatureError:
            return jsonify({'message': 'Token has expired!'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'message': 'Token is invalid!'}), 401

        return f(*args, **kwargs)
    return decorated

# Helper function to get treatment details
def get_treatment_details(treatment_id):
    try:
        response = requests.get(f'http://localhost:5002/treatments/{treatment_id}')
        if response.status_code == 200:
            return response.json()
        return None
    except:
        return None

# Endpoints
@app.route('/appointments', methods=['GET'])
@token_required
def get_appointments():
    user_id = request.user_data['user_id']
    appointments = Appointment.query.filter_by(user_id=user_id).all()
    
    result = []
    for appointment in appointments:
        treatment = get_treatment_details(appointment.treatment_id)
        if treatment:
            result.append({
                'id': appointment.id,
                'treatment': treatment,
                'appointment_date': appointment.appointment_date.strftime('%Y-%m-%d'),
                'appointment_time': appointment.appointment_time,
                'status': appointment.status,
                'notes': appointment.notes,
                'created_at': appointment.created_at.strftime('%Y-%m-%d %H:%M:%S')
            })
    
    return jsonify(result)

@app.route('/appointments/<int:id>', methods=['GET'])
@token_required
def get_appointment(id):
    appointment = Appointment.query.get_or_404(id)
    
    # Check if user has permission to view this appointment
    if appointment.user_id != request.user_data['user_id'] and request.user_data['role'] != 'admin':
        return jsonify({'message': 'Unauthorized access'}), 403
    
    treatment = get_treatment_details(appointment.treatment_id)
    if not treatment:
        return jsonify({'message': 'Treatment not found'}), 404
    
    return jsonify({
        'id': appointment.id,
        'treatment': treatment,
        'appointment_date': appointment.appointment_date.strftime('%Y-%m-%d'),
        'appointment_time': appointment.appointment_time,
        'status': appointment.status,
        'notes': appointment.notes,
        'created_at': appointment.created_at.strftime('%Y-%m-%d %H:%M:%S')
    })

@app.route('/appointments', methods=['POST'])
@token_required
def create_appointment():
    data = request.get_json()
    
    # Validate required fields
    required_fields = ['treatment_id', 'appointment_date', 'appointment_time']
    for field in required_fields:
        if field not in data:
            return jsonify({'message': f'{field} is required'}), 400
    
    # Validate treatment exists
    treatment = get_treatment_details(data['treatment_id'])
    if not treatment:
        return jsonify({'message': 'Treatment not found'}), 404
    
    # Create appointment
    try:
        appointment = Appointment(
            user_id=request.user_data['user_id'],
            treatment_id=data['treatment_id'],
            appointment_date=datetime.strptime(data['appointment_date'], '%Y-%m-%d').date(),
            appointment_time=data['appointment_time'],
            notes=data.get('notes', '')
        )
        db.session.add(appointment)
        db.session.commit()
        
        return jsonify({
            'message': 'Appointment created successfully',
            'appointment': {
                'id': appointment.id,
                'treatment': treatment,
                'appointment_date': appointment.appointment_date.strftime('%Y-%m-%d'),
                'appointment_time': appointment.appointment_time,
                'status': appointment.status,
                'notes': appointment.notes
            }
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': f'Error creating appointment: {str(e)}'}), 500

@app.route('/appointments/<int:id>', methods=['PUT'])
@token_required
def update_appointment(id):
    appointment = Appointment.query.get_or_404(id)
    
    # Check if user has permission to update this appointment
    if appointment.user_id != request.user_data['user_id'] and request.user_data['role'] != 'admin':
        return jsonify({'message': 'Unauthorized access'}), 403
    
    data = request.get_json()
    
    try:
        if 'appointment_date' in data:
            appointment.appointment_date = datetime.strptime(data['appointment_date'], '%Y-%m-%d').date()
        if 'appointment_time' in data:
            appointment.appointment_time = data['appointment_time']
        if 'status' in data and request.user_data['role'] == 'admin':
            appointment.status = data['status']
        if 'notes' in data:
            appointment.notes = data['notes']
        
        db.session.commit()
        
        treatment = get_treatment_details(appointment.treatment_id)
        return jsonify({
            'message': 'Appointment updated successfully',
            'appointment': {
                'id': appointment.id,
                'treatment': treatment,
                'appointment_date': appointment.appointment_date.strftime('%Y-%m-%d'),
                'appointment_time': appointment.appointment_time,
                'status': appointment.status,
                'notes': appointment.notes
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': f'Error updating appointment: {str(e)}'}), 500

@app.route('/appointments/<int:id>', methods=['DELETE'])
@token_required
def delete_appointment(id):
    appointment = Appointment.query.get_or_404(id)
    
    # Check if user has permission to delete this appointment
    if appointment.user_id != request.user_data['user_id'] and request.user_data['role'] != 'admin':
        return jsonify({'message': 'Unauthorized access'}), 403
    
    try:
        db.session.delete(appointment)
        db.session.commit()
        return jsonify({'message': 'Appointment deleted successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': f'Error deleting appointment: {str(e)}'}), 500

# Admin endpoints
@app.route('/admin/appointments', methods=['GET'])
@token_required
def get_all_appointments():
    if request.user_data['role'] != 'admin':
        return jsonify({'message': 'Unauthorized access'}), 403
    
    appointments = Appointment.query.all()
    result = []
    
    for appointment in appointments:
        treatment = get_treatment_details(appointment.treatment_id)
        if treatment:
            result.append({
                'id': appointment.id,
                'user_id': appointment.user_id,
                'treatment': treatment,
                'appointment_date': appointment.appointment_date.strftime('%Y-%m-%d'),
                'appointment_time': appointment.appointment_time,
                'status': appointment.status,
                'notes': appointment.notes,
                'created_at': appointment.created_at.strftime('%Y-%m-%d %H:%M:%S')
            })
    
    return jsonify(result)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5003)
