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
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'payment.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your-secret-key'  # Change this in production

db = SQLAlchemy(app)

# Models
class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(100), nullable=False)
    appointment_id = db.Column(db.Integer, nullable=False)
    amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, completed, failed
    payment_method = db.Column(db.String(50))  # e.g., credit_card, bank_transfer
    transaction_id = db.Column(db.String(100), unique=True)
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

# Helper function to get appointment details
def get_appointment_details(appointment_id):
    try:
        response = requests.get(f'http://localhost:5003/appointments/{appointment_id}', 
                              headers={'Authorization': request.headers.get('Authorization')})
        if response.status_code == 200:
            return response.json()
        return None
    except:
        return None

# Webhook endpoint to receive appointment confirmation
@app.route('/webhook/appointment-confirmed', methods=['POST'])
@token_required
def handle_appointment_confirmed():
    data = request.get_json()
    if not data or 'appointment_id' not in data:
        return jsonify({'message': 'Appointment ID is required'}), 400

    appointment_id = data['appointment_id']
    user_id = data.get('user_id') or request.user_data['user_id']  # Fallback to authenticated user

    # Get appointment details
    appointment = get_appointment_details(appointment_id)
    if not appointment:
        return jsonify({'message': 'Appointment not found'}), 404

    treatment = appointment.get('treatment')
    if not treatment:
        return jsonify({'message': 'Treatment details not available'}), 400

    # Extract price from treatment (assuming price is in treatment data)
    price = float(treatment.get('price', '150000').replace('Rp ', '').replace('.', ''))  # Default to 150000 if not found

    # Check if invoice already exists
    existing_payment = Payment.query.filter_by(appointment_id=appointment_id).first()
    if existing_payment:
        return jsonify({'message': 'Invoice already exists for this appointment'}), 200

    try:
        # Create new payment invoice
        payment = Payment(
            user_id=user_id,
            appointment_id=appointment_id,
            amount=price,
            status='pending'
        )
        db.session.add(payment)
        db.session.commit()

        return jsonify({
            'message': 'Invoice created successfully',
            'payment': {
                'id': payment.id,
                'appointment_id': payment.appointment_id,
                'amount': payment.amount,
                'status': payment.status
            }
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': f'Error creating invoice: {str(e)}'}), 500

# Endpoints
@app.route('/payments/invoices', methods=['GET'])
@token_required
def get_invoices():
    user_id = request.user_data['user_id']
    appointment_id = request.args.get('appointment_id')

    query = Payment.query.filter_by(user_id=user_id, status='pending')
    if appointment_id:
        query = query.filter_by(appointment_id=appointment_id)

    payments = query.all()
    
    result = []
    for payment in payments:
        appointment = get_appointment_details(payment.appointment_id)
        if appointment:
            result.append({
                'id': payment.id,
                'appointment_id': payment.appointment_id,
                'treatment': appointment['treatment']['name'],
                'appointment_date': appointment['appointment_date'],
                'amount': payment.amount,
                'status': payment.status,
                'created_at': payment.created_at.strftime('%Y-%m-%d %H:%M:%S')
            })
    
    return jsonify(result)

@app.route('/payments/history', methods=['GET'])
@token_required
def get_payment_history():
    user_id = request.user_data['user_id']
    payments = Payment.query.filter_by(user_id=user_id).all()
    
    result = []
    for payment in payments:
        appointment = get_appointment_details(payment.appointment_id)
        if appointment:
            result.append({
                'id': payment.id,
                'appointment_id': payment.appointment_id,
                'treatment': appointment['treatment']['name'],
                'appointment_date': appointment['appointment_date'],
                'amount': payment.amount,
                'status': payment.status,
                'payment_method': payment.payment_method,
                'transaction_id': payment.transaction_id,
                'created_at': payment.created_at.strftime('%Y-%m-%d %H:%M:%S')
            })
    
    return jsonify(result)

@app.route('/payments/<int:id>/process', methods=['POST'])
@token_required
def process_payment(id):
    payment = Payment.query.get_or_404(id)
    
    if payment.user_id != request.user_data['user_id']:
        return jsonify({'message': 'Unauthorized access'}), 403
    
    if payment.status != 'pending':
        return jsonify({'message': 'Payment already processed'}), 400
    
    data = request.get_json()
    if 'payment_method' not in data:
        return jsonify({'message': 'Payment method is required'}), 400
    
    try:
        # Simulate payment processing
        import uuid
        payment.status = 'completed'
        payment.payment_method = data['payment_method']
        payment.transaction_id = str(uuid.uuid4())
        payment.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            'message': 'Payment processed successfully',
            'payment': {
                'id': payment.id,
                'appointment_id': payment.appointment_id,
                'amount': payment.amount,
                'status': payment.status,
                'payment_method': payment.payment_method,
                'transaction_id': payment.transaction_id
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': f'Error processing payment: {str(e)}'}), 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5004)