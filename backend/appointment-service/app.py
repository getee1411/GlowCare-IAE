from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import jwt
from functools import wraps
import os
from flask_cors import CORS
import pika
import json

app = Flask(__name__)
CORS(app)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///appointments.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key')

db = SQLAlchemy(app)

# Models
class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, nullable=False)
    doctor_id = db.Column(db.Integer, nullable=False)
    treatment_id = db.Column(db.Integer, nullable=False)
    appointment_date = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, confirmed, cancelled, completed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text)
    provider_id = db.Column(db.Integer, nullable=True)  # ID of the service provider
    consumer_id = db.Column(db.Integer, nullable=True)  # ID of the service consumer

# RabbitMQ connection
def get_rabbitmq_connection():
    return pika.BlockingConnection(pika.ConnectionParameters('localhost'))

# Message Queue Publisher
def publish_message(queue_name, message):
    connection = get_rabbitmq_connection()
    channel = connection.channel()
    channel.queue_declare(queue=queue_name)
    channel.basic_publish(
        exchange='',
        routing_key=queue_name,
        body=json.dumps(message)
    )
    connection.close()

# Token verification decorator
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'message': 'Token is missing!'}), 401
        try:
            token = token.split(' ')[1]  # Remove 'Bearer ' prefix
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user = data
        except:
            return jsonify({'message': 'Token is invalid!'}), 401
        return f(current_user, *args, **kwargs)
    return decorated

# Routes
@app.route('/appointments', methods=['POST'])
@token_required
def create_appointment(current_user):
    data = request.get_json()
    
    new_appointment = Appointment(
        patient_id=current_user['id'],
        doctor_id=data['doctor_id'],
        treatment_id=data['treatment_id'],
        appointment_date=datetime.fromisoformat(data['appointment_date']),
        notes=data.get('notes', ''),
        provider_id=data.get('provider_id'),
        consumer_id=data.get('consumer_id')
    )
    
    db.session.add(new_appointment)
    db.session.commit()
    
    # Publish appointment creation event
    publish_message('appointment_created', {
        'appointment_id': new_appointment.id,
        'patient_id': new_appointment.patient_id,
        'doctor_id': new_appointment.doctor_id,
        'appointment_date': new_appointment.appointment_date.isoformat()
    })
    
    return jsonify({
        'message': 'Appointment created successfully',
        'appointment_id': new_appointment.id
    }), 201

@app.route('/appointments', methods=['GET'])
@token_required
def get_appointments(current_user):
    if current_user['role'] == 'admin':
        appointments = Appointment.query.all()
    elif current_user['role'] == 'doctor':
        appointments = Appointment.query.filter_by(doctor_id=current_user['id']).all()
    elif current_user['role'] == 'provider':
        appointments = Appointment.query.filter_by(provider_id=current_user['id']).all()
    elif current_user['role'] == 'consumer':
        appointments = Appointment.query.filter_by(consumer_id=current_user['id']).all()
    else:  # patient
        appointments = Appointment.query.filter_by(patient_id=current_user['id']).all()
    
    return jsonify([{
        'id': apt.id,
        'patient_id': apt.patient_id,
        'doctor_id': apt.doctor_id,
        'treatment_id': apt.treatment_id,
        'appointment_date': apt.appointment_date.isoformat(),
        'status': apt.status,
        'notes': apt.notes,
        'provider_id': apt.provider_id,
        'consumer_id': apt.consumer_id
    } for apt in appointments])

@app.route('/appointments/<int:appointment_id>', methods=['PUT'])
@token_required
def update_appointment(current_user, appointment_id):
    appointment = Appointment.query.get_or_404(appointment_id)
    
    # Check authorization
    if current_user['role'] not in ['admin', 'doctor', 'provider'] and appointment.patient_id != current_user['id']:
        return jsonify({'message': 'Unauthorized'}), 403
    
    data = request.get_json()
    
    if 'status' in data:
        appointment.status = data['status']
        # Publish status update event
        publish_message('appointment_status_updated', {
            'appointment_id': appointment.id,
            'new_status': data['status']
        })
    if 'notes' in data:
        appointment.notes = data['notes']
    if 'appointment_date' in data:
        appointment.appointment_date = datetime.fromisoformat(data['appointment_date'])
    
    db.session.commit()
    return jsonify({'message': 'Appointment updated successfully'})

@app.route('/appointments/<int:appointment_id>', methods=['DELETE'])
@token_required
def delete_appointment(current_user, appointment_id):
    appointment = Appointment.query.get_or_404(appointment_id)
    
    # Check authorization
    if current_user['role'] not in ['admin', 'doctor', 'provider'] and appointment.patient_id != current_user['id']:
        return jsonify({'message': 'Unauthorized'}), 403
    
    db.session.delete(appointment)
    db.session.commit()
    
    # Publish appointment deletion event
    publish_message('appointment_deleted', {
        'appointment_id': appointment_id
    })
    
    return jsonify({'message': 'Appointment deleted successfully'})

# Provider specific routes
@app.route('/provider/appointments', methods=['GET'])
@token_required
def get_provider_appointments(current_user):
    if current_user['role'] != 'provider':
        return jsonify({'message': 'Unauthorized'}), 403
    
    appointments = Appointment.query.filter_by(provider_id=current_user['id']).all()
    return jsonify([{
        'id': apt.id,
        'patient_id': apt.patient_id,
        'doctor_id': apt.doctor_id,
        'treatment_id': apt.treatment_id,
        'appointment_date': apt.appointment_date.isoformat(),
        'status': apt.status,
        'notes': apt.notes
    } for apt in appointments])

# Consumer specific routes
@app.route('/consumer/appointments', methods=['GET'])
@token_required
def get_consumer_appointments(current_user):
    if current_user['role'] != 'consumer':
        return jsonify({'message': 'Unauthorized'}), 403
    
    appointments = Appointment.query.filter_by(consumer_id=current_user['id']).all()
    return jsonify([{
        'id': apt.id,
        'patient_id': apt.patient_id,
        'doctor_id': apt.doctor_id,
        'treatment_id': apt.treatment_id,
        'appointment_date': apt.appointment_date.isoformat(),
        'status': apt.status,
        'notes': apt.notes
    } for apt in appointments])

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5003)
