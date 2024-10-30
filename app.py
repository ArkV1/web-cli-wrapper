from flask import Flask
from src.routes import register_routes
from src.api_routes import register_api_routes

app = Flask(__name__)
register_routes(app)
register_api_routes(app)

if __name__ == '__main__':
    app.run()
