from flask import Flask, jsonify
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity

app = Flask(__name__)
app.config["JWT_SECRET_KEY"] = "super-secret"
jwt = JWTManager(app)

# Mock user DB with roles
users = {
    "alice": {"password": "pass123", "role": "admin"},
    "bob": {"password": "mypassword", "role": "user"}
}

@app.route("/login", methods=["POST"])
def login():
    # Example: normally you'd check request.json
    username, password = "alice", "pass123"
    if username in users and users[username]["password"] == password:
        token = create_access_token(identity={"username": username, "role": users[username]["role"]})
        return jsonify(access_token=token)
    return jsonify(msg="Bad credentials"), 401

@app.route("/admin-only", methods=["GET"])
@jwt_required()
def admin_only():
    current_user = get_jwt_identity()
    if current_user["role"] != "admin":
        return jsonify(msg="Not authorized"), 403
    return jsonify(msg=f"Welcome Admin {current_user['username']}!")

if __name__ == "__main__":
    app.run(debug=True)
