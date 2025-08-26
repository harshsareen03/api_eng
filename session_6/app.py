from flask import Flask, render_template, request, jsonify, redirect, url_for, Response
from models import db, User
from auth import bcrypt, login_manager
from ariadne import QueryType, MutationType, make_executable_schema, graphql_sync
from ariadne.explorer import ExplorerPlayground  # modern Playground replacement
from flask_login import login_user, logout_user, current_user
# Flask app setup
app = Flask(__name__)
app.config["SECRET_KEY"] = "super-secret"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///users.db"

db.init_app(app)
bcrypt.init_app(app)
login_manager.init_app(app)

with app.app_context():
    db.create_all()

# ---------------- GraphQL Schema ---------------- #
type_defs = """
    type Query {
        users: [User!]
    }

    type User {
        id: ID!
        username: String!
    }

    type Mutation {
        register(username: String!, password: String!): String
        login(username: String!, password: String!): String
        logout: String
    }
"""

query = QueryType()
mutation = MutationType()

@query.field("users")
def resolve_users(*_):
    return User.query.all()
# --- login manager ---
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@mutation.field("login")
def resolve_login(_, info, username, password):
    user = User.query.filter_by(username=username).first()
    if user and bcrypt.check_password_hash(user.password, password):
        login_user(user)  # <-- now works, Flask-Login handles the session
        return f"Welcome back {user.username}!"
    return "Invalid username or password"

@mutation.field("logout")
def resolve_logout(_, info):
    if current_user.is_authenticated:
        logout_user()
        return "Logged out successfully"
    return "No active session"
@mutation.field("register")
def resolve_register(_, info, username, password):
    if User.query.filter_by(username=username).first():
        return "User already exists"
    hashed_pw = bcrypt.generate_password_hash(password).decode("utf-8")
    user = User(username=username, password=hashed_pw)
    db.session.add(user)
    db.session.commit()
    return "User registered successfully"

schema = make_executable_schema(type_defs, [query, mutation])





# ---------------- GraphQL Endpoints ---------------- #
@app.route("/graphql", methods=["GET"])
def graphql_playground():
    # Modern GraphQL explorer
    return ExplorerPlayground().html(request), 200

@app.route("/graphql", methods=["POST"])
def graphql_server():
    data = request.get_json()
    success, result = graphql_sync(schema, data, context_value=request, debug=True)
    return jsonify(result)

# ---------------- Web Routes ---------------- #
@app.route("/")
def home():
    return render_template("login.html")

if __name__ == "__main__":
    app.run(debug=True)
