import os
import sys

import pytest
from flask import Flask
from flask_jwt_extended import create_access_token

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from backend.extensions import db, jwt, migrate
from backend.routes.auth import auth_bp
from backend.routes.usuarios import usuarios_bp
from backend.routes.regionais import regionais_bp
from backend.routes.empreendimentos import empreendimentos_bp
from backend.routes.atividades import atividades_bp
from backend.routes.rotinas import rotinas_bp
from backend.routes.notificacoes import notificacoes_bp
from backend.models import Usuario, Regional, AtividadeCatalogo, Rotina


@pytest.fixture()
def app():
    flask_app = Flask(__name__)
    flask_app.config.update(
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        JWT_SECRET_KEY='test-secret-key',
        SECRET_KEY='test-secret-key',
        TESTING=True,
        UPLOAD_FOLDER='/tmp',
    )
    db.init_app(flask_app)
    jwt.init_app(flask_app)
    migrate.init_app(flask_app, db)

    flask_app.register_blueprint(auth_bp, url_prefix='/api/auth')
    flask_app.register_blueprint(usuarios_bp, url_prefix='/api/usuarios')
    flask_app.register_blueprint(regionais_bp, url_prefix='/api/regionais')
    flask_app.register_blueprint(empreendimentos_bp, url_prefix='/api/empreendimentos')
    flask_app.register_blueprint(atividades_bp, url_prefix='/api/atividades')
    flask_app.register_blueprint(rotinas_bp, url_prefix='/api/rotinas')
    flask_app.register_blueprint(notificacoes_bp, url_prefix='/api/notificacoes')

    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


class Factory:
    """Pequenas fábricas de dados de teste — mantém os testes focados no
    comportamento, não na criação de fixtures repetitivas."""

    def regional(self, nome='Regional Teste'):
        r = Regional(nome=nome)
        db.session.add(r)
        db.session.commit()
        return r

    def usuario(self, nome, email, perfil, regional_id=None, status='ativo', supervisor_id=None):
        u = Usuario(
            nome=nome, email=email, perfil=perfil, regional_id=regional_id,
            status=status, supervisor_id=supervisor_id,
        )
        u.set_senha('teste123')
        db.session.add(u)
        db.session.commit()
        return u

    def atividade(self, nome, periodicidade, perfil, obrigatoria=True, ativo=True):
        a = AtividadeCatalogo(
            nome=nome, periodicidade=periodicidade, perfil=perfil,
            obrigatoria=obrigatoria, ativo=ativo,
        )
        db.session.add(a)
        db.session.commit()
        return a

    def rotina(self, usuario, atividade, periodo_inicio, periodo_fim, periodicidade=None, status='nao_iniciada'):
        r = Rotina(
            usuario_id=usuario.id, atividade_id=atividade.id,
            periodo_inicio=periodo_inicio, periodo_fim=periodo_fim,
            periodicidade=periodicidade or atividade.periodicidade, status=status,
        )
        db.session.add(r)
        db.session.commit()
        return r


@pytest.fixture()
def factory(app):
    return Factory()


def auth_headers(user):
    token = create_access_token(identity=str(user.id))
    return {'Authorization': f'Bearer {token}'}
