from flask import Flask, request, jsonify
from flask_bcrypt import Bcrypt
from flask_jwt_extended import (
    JWTManager, create_access_token, create_refresh_token,
    jwt_required, get_jwt_identity, get_jwt
)
from config import Config
from models import db, User, Post
from auth import role_required

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)
bcrypt = Bcrypt(app)
jwt = JWTManager(app)

# Create DB tables
with app.app_context():
    db.create_all()

# -------------------------
# Auth endpoints
# -------------------------
@app.route("/register", methods=["POST"])
def register():
    data = request.get_json() or {}
    username = data.get("username")
    password = data.get("password")
    role = data.get("role", "viewer")
    if not username or not password:
        return jsonify({"msg": "username and password required"}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({"msg": "user already exists"}), 409

    pw_hash = bcrypt.generate_password_hash(password).decode("utf-8")
    user = User(username=username, password=pw_hash, role=role)
    db.session.add(user)
    db.session.commit()
    return jsonify({"msg": "user created", "user": user.to_dict()}), 201

@app.route("/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    username = data.get("username")
    password = data.get("password")
    if not username or not password:
        return jsonify({"msg": "username & password required"}), 400
    user = User.query.filter_by(username=username).first()
    if not user or not bcrypt.check_password_hash(user.password, password):
        return jsonify({"msg": "invalid credentials"}), 401

    additional_claims = {"role": user.role}
    access_token = create_access_token(identity=str(user.id), additional_claims={"role": user.role})
    refresh_token = create_refresh_token(identity=str(user.id), additional_claims={"role": user.role})

    return jsonify({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": user.to_dict()
    }), 200

@app.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh():
    identity = get_jwt_identity()
    user = User.query.get(identity)
    if not user:
        return jsonify({"msg": "user not found"}), 404
    additional_claims = {"role": user.role}
    new_access = create_access_token(identity=identity, additional_claims=additional_claims)
    return jsonify({"access_token": new_access}), 200

# -------------------------
# Admin endpoints (manage users)
# -------------------------
@app.route("/admin/users", methods=["GET"])
@jwt_required()
@role_required("admin")
def list_users():
    users = [u.to_dict() for u in User.query.all()]
    return jsonify(users), 200

@app.route("/admin/users/<int:user_id>", methods=["PATCH"])
@jwt_required()
@role_required("admin")
def update_user_role(user_id):
    data = request.get_json() or {}
    new_role = data.get("role")
    if new_role not in ("admin", "editor", "viewer"):
        return jsonify({"msg": "invalid role"}), 400
    user = User.query.get(user_id)
    if not user:
        return jsonify({"msg": "user not found"}), 404
    user.role = new_role
    db.session.commit()
    return jsonify({"msg": "role updated", "user": user.to_dict()}), 200

@app.route("/admin/users/<int:user_id>", methods=["DELETE"])
@jwt_required()
@role_required("admin")
def delete_user(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"msg": "user not found"}), 404
    db.session.delete(user)
    db.session.commit()
    return jsonify({"msg": "user deleted"}), 200

# -------------------------
# Editor endpoints (create/update posts)
# -------------------------
@app.route("/posts", methods=["POST"])
@jwt_required()
@role_required("admin", "editor")
def create_post():
    data = request.get_json() or {}
    title = data.get("title")
    content = data.get("content")
    if not title or not content:
        return jsonify({"msg": "title & content required"}), 400
    author_id = get_jwt_identity()
    post = Post(title=title, content=content, author_id=author_id)
    db.session.add(post)
    db.session.commit()
    return jsonify({"msg": "post created", "post": post.to_dict()}), 201

@app.route("/posts/<int:post_id>", methods=["PATCH"])
@jwt_required()
@role_required("admin", "editor")
def update_post(post_id):
    post = Post.query.get(post_id)
    if not post:
        return jsonify({"msg": "post not found"}), 404
    data = request.get_json() or {}
    title = data.get("title")
    content = data.get("content")
    if title:
        post.title = title
    if content:
        post.content = content
    db.session.commit()
    return jsonify({"msg": "post updated", "post": post.to_dict()}), 200

# -------------------------
# Viewer endpoints (read-only)
# -------------------------
@app.route("/posts", methods=["GET"])
@jwt_required(optional=True)
def list_posts():
    posts = [p.to_dict() for p in Post.query.all()]
    return jsonify(posts), 200

@app.route("/posts/<int:post_id>", methods=["GET"])
@jwt_required(optional=True)
def get_post(post_id):
    post = Post.query.get(post_id)
    if not post:
        return jsonify({"msg": "post not found"}), 404
    return jsonify(post.to_dict()), 200

# -------------------------
# Utility endpoint: whoami
# -------------------------
@app.route("/me", methods=["GET"])
@jwt_required()
def me():
    uid = get_jwt_identity()
    user = User.query.get(uid)
    return jsonify({"user": user.to_dict()}), 200

# -------------------------
# Error handlers (basic)
# -------------------------
@app.errorhandler(404)
def not_found(e):
    return jsonify({"msg": "not found"}), 404

if __name__ == "__main__":
    app.run(debug=True)
