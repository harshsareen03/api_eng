from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)


''' type of factors
# password
# mfa(multi factor authentication)
# token based authentication
# certificate based authentication (pki,vpns)
# single sign on(sso)
'''

''' authentication protocols

# basic authentication
# kerberos
# openid connectq
# saml(security assertion markup language)-xml based
# oauth2.0
# digest authentication

'''

'''authentication lifecycle

1)registration
2)login
3)verfication
4)session creation
5)re-authentication'''

'''
coomon attcaks on authetication
1)phising
2)brute force attack
3)credential stuffing
4)MAN IN THE MIDDLE ATTACK
5)SESSION HIJACKING

'''