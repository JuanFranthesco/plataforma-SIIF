from app import create_app
import os

app = create_app()

if __name__ == '__main__':
    debug = os.getenv("DEBUG", True)

    app.run(debug=debug)
