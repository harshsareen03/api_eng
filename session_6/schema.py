import graphene
from graphene_sqlalchemy import SQLAlchemyObjectType
from models import User, db
from flask_bcrypt import check_password_hash, generate_password_hash
from flask_login import login_user, logout_user, current_user

class UserObject(SQLAlchemyObjectType):
    class Meta:
        model = User

class RegisterUser(graphene.Mutation):
    class Arguments:
        username = graphene.String(required=True)
        password = graphene.String(required=True)

    ok = graphene.Boolean()
    user = graphene.Field(lambda: UserObject)

    def mutate(self, info, username, password):
        hashed_pw = generate_password_hash(password).decode("utf-8")
        new_user = User(username=username, password=hashed_pw)
        db.session.add(new_user)
        db.session.commit()
        return RegisterUser(user=new_user, ok=True)

class LoginUser(graphene.Mutation):
    class Arguments:
        username = graphene.String(required=True)
        password = graphene.String(required=True)

    ok = graphene.Boolean()

    def mutate(self, info, username, password):
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return LoginUser(ok=True)
        return LoginUser(ok=False)

class LogoutUser(graphene.Mutation):
    ok = graphene.Boolean()

    def mutate(self, info):
        logout_user()
        return LogoutUser(ok=True)

class Query(graphene.ObjectType):
    me = graphene.Field(UserObject)

    def resolve_me(self, info):
        if not current_user.is_authenticated:
            return None
        return current_user

class Mutation(graphene.ObjectType):
    register_user = RegisterUser.Field()
    login_user = LoginUser.Field()
    logout_user = LogoutUser.Field()

schema = graphene.Schema(query=Query, mutation=Mutation)
