from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import os

app = Flask(__name__)
CORS(app)  # Enable CORS
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'treatment.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Model
class Treatment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nama = db.Column(db.String(100), nullable=False)
    nama_dokter = db.Column(db.String(100), nullable=False)
    harga = db.Column(db.Integer, nullable=False)

# Inisialisasi data awal
def seed_data():
    if Treatment.query.count() == 0:
        data = [
            {"id": 1, "nama": "Facial Glow Up", "nama_dokter": "dr. Ayu Pratiwi", "harga": 150000},
            {"id": 2, "nama": "Chemical Peeling", "nama_dokter": "dr. Rina Kartika", "harga": 200000},
            {"id": 3, "nama": "Microneedling", "nama_dokter": "dr. Budi Santoso", "harga": 300000},
            {"id": 4, "nama": "Laser Rejuvenation", "nama_dokter": "dr. Intan Permata", "harga": 500000},
            {"id": 5, "nama": "Botox Treatment", "nama_dokter": "dr. Ahmad Yusuf", "harga": 750000},
            {"id": 6, "nama": "Filler Injection", "nama_dokter": "dr. Clara Wijaya", "harga": 850000},
            {"id": 7, "nama": "Acne Treatment", "nama_dokter": "dr. Rendy Prakoso", "harga": 180000},
            {"id": 8, "nama": "Whitening Infusion", "nama_dokter": "dr. Sari Utami", "harga": 250000},
            {"id": 9, "nama": "Anti Aging Therapy", "nama_dokter": "dr. Andika Putra", "harga": 650000},
            {"id": 10, "nama": "Hydra Facial", "nama_dokter": "dr. Melinda Harun", "harga": 275000}
        ]
        for item in data:
            treatment = Treatment(**item)
            db.session.add(treatment)
        db.session.commit()

# Endpoint CRUD
@app.route('/treatments', methods=['GET'])
def get_all_treatments():
    treatments = Treatment.query.all()
    return jsonify([{
        'id': t.id,
        'nama': t.nama,
        'nama_dokter': t.nama_dokter,
        'harga': t.harga
    } for t in treatments])

@app.route('/treatments/<int:id>', methods=['GET'])
def get_treatment(id):
    treatment = Treatment.query.get_or_404(id)
    return jsonify({
        'id': treatment.id,
        'nama': treatment.nama,
        'nama_dokter': treatment.nama_dokter,
        'harga': treatment.harga
    })

@app.route('/treatments', methods=['POST'])
def add_treatment():
    data = request.get_json()
    treatment = Treatment(
        nama=data['nama'],
        nama_dokter=data['nama_dokter'],
        harga=data['harga']
    )
    db.session.add(treatment)
    db.session.commit()
    return jsonify({'message': 'Treatment added successfully'}), 201

@app.route('/treatments/<int:id>', methods=['PUT'])
def update_treatment(id):
    treatment = Treatment.query.get_or_404(id)
    data = request.get_json()
    treatment.nama = data.get('nama', treatment.nama)
    treatment.nama_dokter = data.get('nama_dokter', treatment.nama_dokter)
    treatment.harga = data.get('harga', treatment.harga)
    db.session.commit()
    return jsonify({'message': 'Treatment updated successfully'})

@app.route('/treatments/<int:id>', methods=['DELETE'])
def delete_treatment(id):
    treatment = Treatment.query.get_or_404(id)
    db.session.delete(treatment)
    db.session.commit()
    return jsonify({'message': 'Treatment deleted successfully'})

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        seed_data()
    app.run(debug=True) 