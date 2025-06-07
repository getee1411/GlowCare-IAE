from flask import Flask, request, jsonify
from functools import wraps
import jwt
import datetime
import pymysql.cursors
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'GlowCare'

DB_CONFIG = {
    'host': '127.0.0.1',
    'user': 'root',
    'password': '',
    'db': 'user_service_db',
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}

def get_db_connection():
    try:
        connection = pymysql.connect(**DB_CONFIG)
        return connection
    except Exception as e:
        print(f"Error connecting to database: {e}")
        return None

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

def roles_required(roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not hasattr(request, 'user_data') or 'role' not in request.user_data:
                return jsonify({'message': 'Role information not found in token.'}), 403
            
            user_role = request.user_data['role']
            if user_role not in roles:
                return jsonify({'message': 'Access forbidden: Insufficient role.'}), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    role = data.get('role', 'pasien')
    address = data.get('address')
    phone_number = data.get('phone_number')
    
    if not username or not password:
        return jsonify({'message': 'Username and password are required!'}), 400

    connection = get_db_connection()
    if connection is None:
        return jsonify({'message': 'Database connection error!'}), 500

    try:
        with connection.cursor() as cursor:
            sql = "SELECT id FROM users WHERE username = %s"
            cursor.execute(sql, (username,))
            result = cursor.fetchone()
            if result:
                return jsonify({'message': 'User already exists!'}), 409

            sql = """
                INSERT INTO users (username, password, role, address, phone_number)
                VALUES (%s, %s, %s, %s, %s)
            """
            cursor.execute(sql, (username, password, role, address, phone_number))
        connection.commit()
        return jsonify({'message': 'User registered successfully!', 'user': {'username': username, 'role': role}}), 201
    except Exception as e:
        connection.rollback()
        return jsonify({'message': f'Error registering user: {e}'}), 500
    finally:
        connection.close()

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({'message': 'Username and password are required!'}), 400

    connection = get_db_connection()
    if connection is None:
        return jsonify({'message': 'Database connection error!'}), 500

    try:
        with connection.cursor() as cursor:
            sql = "SELECT id, username, password, role FROM users WHERE username = %s"
            cursor.execute(sql, (username,))
            user = cursor.fetchone()

            if not user or user['password'] != password:
                return jsonify({'message': 'Invalid credentials!'}), 401

            token_payload = {
                'user_id': user['username'],
                'role': user['role'],
                'exp': datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=30)
            }
            token = jwt.encode(token_payload, app.config['SECRET_KEY'], algorithm="HS256")

            return jsonify({'token': token})
    except Exception as e:
        return jsonify({'message': f'Error during login: {e}'}), 500
    finally:
        connection.close()

@app.route('/profile', methods=['GET'])
@token_required
def get_profile():
    user_id_from_token = request.user_data['user_id']
    
    connection = get_db_connection()
    if connection is None:
        return jsonify({'message': 'Database connection error!'}), 500
    
    try:
        with connection.cursor() as cursor:
            sql = """
                SELECT username, role, address, phone_number
                FROM users WHERE username = %s
            """
            cursor.execute(sql, (user_id_from_token,))
            user_data = cursor.fetchone()
            
            if not user_data:
                return jsonify({'message': 'User profile not found!'}), 404
            
            profile_data = {
                "username": user_data['username'],
                "role": user_data['role'],
                "address": user_data['address'],
                "phone_number": user_data['phone_number']
            }
            return jsonify({'profile': profile_data})
    except Exception as e:
        return jsonify({'message': f'Error fetching profile: {e}'}), 500
    finally:
        connection.close()

@app.route('/profile/edit', methods=['PUT'])
@token_required
def edit_profile():
    user_id_from_token = request.user_data['user_id']
    data = request.get_json()

    address = data.get('address')
    phone_number = data.get('phone_number')
        
    connection = get_db_connection()
    if connection is None:
        return jsonify({'message': 'Database connection error!'}), 500

    try:
        with connection.cursor() as cursor:
            update_fields = []
            update_values = []

            if address is not None:
                update_fields.append("address = %s")
                update_values.append(address)
            if phone_number is not None:
                update_fields.append("phone_number = %s")
                update_values.append(phone_number)

            if not update_fields:
                return jsonify({'message': 'No fields provided for update!'}), 400

            sql = f"UPDATE users SET {', '.join(update_fields)} WHERE username = %s"
            update_values.append(user_id_from_token)

            cursor.execute(sql, tuple(update_values))
            connection.commit()

            if cursor.rowcount == 0:
                return jsonify({'message': 'User not found or no changes applied!'}), 404
            
            return jsonify({'message': 'Profile updated successfully!'}), 200
    except Exception as e:
        connection.rollback()
        return jsonify({'message': f'Error updating profile: {e}'}), 500
    finally:
        connection.close()

@app.route('/admin_data', methods=['GET'])
@token_required
@roles_required(['admin'])
def get_admin_data():
    return jsonify({'message': 'This is sensitive data for admins only!'})

if __name__ == '__main__':
    app.run(debug=True, port=5001)