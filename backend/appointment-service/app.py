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
    appointment_date = db.Column(db.String(10), nullable=False)
    appointment_time = db.Column(db.String(5), nullable=False)
    status = db.Column(db.String(20), default='confirmed')  # Default to confirmed
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
        response = requests.get(f'http://localhost:5002/treatments/{treatment_id}', 
                              headers={'Authorization': request.headers.get('Authorization')})
        if response.status_code == 200:
            return response.json()
        return None
    except:
        return None

# Endpoints
@app.route('/appointments', methods=['POST'])
@token_required
def create_appointment():
    data = request.get_json()
    required_fields = ['treatment_id', 'appointment_date', 'appointment_time']
    for field in required_fields:
        if field not in data:
            return jsonify({'message': f'{field} is required'}), 400
    
    try:
        appointment = Appointment(
            user_id=data['user_id'],
            treatment_id=data['treatment_id'],
            appointment_date=data['appointment_date'],
            appointment_time=data['appointment_time'],
            notes=data.get('notes'),
            status='confirmed'  # Auto-confirmed
        )
        db.session.add(appointment)
        db.session.commit()

        # Notify Payment Service to create invoice
        webhook_data = {
            'appointment_id': appointment.id,
            'user_id': appointment.user_id
        }
        response = requests.post('http://localhost:5004/webhook/appointment-confirmed', 
                               json=webhook_data, 
                               headers={'Authorization': request.headers.get('Authorization')})
        if response.status_code != 201:
            print(f"Warning: Failed to create invoice. Response: {response.text}")

        return jsonify({
            'message': 'Appointment created successfully',
            'appointment': {
                'id': appointment.id,
                'user_id': appointment.user_id,
                'treatment_id': appointment.treatment_id,
                'appointment_date': appointment.appointment_date,
                'appointment_time': appointment.appointment_time,
                'status': appointment.status
            }
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': f'Error creating appointment: {str(e)}'}), 500

@app.route('/appointments/<int:id>', methods=['GET'])
@token_required
def get_appointment(id):
    appointment = Appointment.query.get_or_404(id)
    if appointment.user_id != request.user_data['user_id'] and request.user_data['role'] != 'admin':
        return jsonify({'message': 'Unauthorized access'}), 403
    
    treatment = get_treatment_details(appointment.treatment_id)
    return jsonify({
        'id': appointment.id,
        'user_id': appointment.user_id,
        'treatment': treatment,
        'appointment_date': appointment.appointment_date,
        'appointment_time': appointment.appointment_time,
        'status': appointment.status,
        'notes': appointment.notes,
        'created_at': appointment.created_at.strftime('%Y-%m-%d %H:%M:%S')
    })

@app.route('/appointments/<int:id>', methods=['PUT'])
@token_required
def update_appointment(id):
    appointment = Appointment.query.get_or_404(id)
    if appointment.user_id != request.user_data['user_id'] and request.user_data['role'] != 'admin':
        return jsonify({'message': 'Unauthorized access'}), 403
    
    data = request.get_json()
    try:
        if 'appointment_date' in data:
            appointment.appointment_date = data['appointment_date']
        if 'appointment_time' in data:
            appointment.appointment_time = data['appointment_time']
        if 'status' in data:
            appointment.status = data['status']
        if 'notes' in data:
            appointment.notes = data['notes']
        appointment.updated_at = datetime.utcnow()

        db.session.commit()

        return jsonify({
            'message': 'Appointment updated successfully',
            'appointment': {
                'id': appointment.id,
                'user_id': appointment.user_id,
                'treatment_id': appointment.treatment_id,
                'appointment_date': appointment.appointment_date,
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
    if appointment.user_id != request.user_data['user_id'] and request.user_data['role'] != 'admin':
        return jsonify({'message': 'Unauthorized access'}), 403
    
    try:
        db.session.delete(appointment)
        db.session.commit()
        return jsonify({'message': 'Appointment deleted successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': f'Error deleting appointment: {str(e)}'}), 500

@app.route('/admin/appointments', methods=['GET'])
@token_required
def get_all_appointments():
    if request.user_data['role'] != 'admin':
        return jsonify({'message': 'Unauthorized access'}), 403
    
    appointments = Appointment.query.all()
    result = []
    for appointment in appointments:
        treatment = get_treatment_details(appointment.treatment_id)
        result.append({
            'id': appointment.id,
            'user_id': appointment.user_id,
            'treatment': treatment,
            'appointment_date': appointment.appointment_date,
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